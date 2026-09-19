"""The one definition of "spending" and "income", and of what a date window means.

Every surface that shows a money figure -- dashboard tiles, the chat
agent's tools, the MCP server -- goes through this module, so the number on
the home screen and the number in a chat reply can never disagree.

Definitions (chosen to match what a bank statement shows):
- Spending = outflows in expense categories MINUS refunds in those same
  categories. A $60 return nets against the $100 purchase, like it does on
  the card statement. Netting happens within each top-level category and
  floors at zero (see spend_query), so a big refund can't produce "negative
  spending". Transfers between the user's own accounts (including
  credit-card payments) are a separate category type and never count.
- Income = net amount in income categories.
- Pending transactions are included (the money is committed) and reported
  separately as `pending_amount` so an answer can say "$X of that is still
  pending".

Windows are resolved here, never by the model: the agent names a window
("last_week") or gives explicit dates, and every result echoes the exact
resolved start/end so the reply can state -- and the user can check -- the
dates it covers. "Today" is taken in the user's timezone.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import get_close_matches
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.db.models import Category, LinkedAccount, Transaction, User
from app.db.seed_categories import seed_default_categories

NAMED_WINDOWS = (
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "this_year",
    "last_year",
    "last_7_days",
    "last_30_days",
    "last_90_days",
)
# Calendar periods that are still in progress: comparing one against the
# full previous period is apples-to-oranges, so compare_spending also
# returns the previous period cut off at the same point.
_IN_PROGRESS_PREVIOUS = {"this_week": "last_week", "this_month": "last_month", "this_year": "last_year"}

# Legacy trailing periods used by the dashboard's week/month/year toggle.
# Mapped to calendar periods-to-date rather than trailing 7/30/365 days,
# because "Spending this month" on screen must mean since the 1st.
LEGACY_PERIODS = {"week": "this_week", "month": "this_month", "year": "this_year"}

# Everyday words for Bankr categories. The model is told the canonical
# names, but users say "eating out", and a miss here would otherwise be a
# confidently wrong $0.
CATEGORY_ALIASES: dict[str, str] = {
    "eating out": "Dining",
    "food out": "Dining",
    "restaurant": "Restaurants",
    "takeout": "Dining",
    "take out": "Dining",
    "delivery": "Dining",
    "food delivery": "Dining",
    "fast food": "Fast Food",
    "coffee shops": "Coffee",
    "cafes": "Coffee",
    "bars": "Alcohol & Bars",
    "alcohol": "Alcohol & Bars",
    "drinks": "Alcohol & Bars",
    "grocery": "Groceries",
    "supermarket": "Groceries",
    "food shopping": "Groceries",
    "gas": "Gas",
    "gasoline": "Gas",
    "fuel": "Gas",
    "gas station": "Gas",
    "gas stations": "Gas",
    "petrol": "Gas",
    "uber": "Rideshare & Taxi",
    "lyft": "Rideshare & Taxi",
    "rideshare": "Rideshare & Taxi",
    "taxi": "Rideshare & Taxi",
    "transit": "Public Transit",
    "subway": "Public Transit",
    "train": "Public Transit",
    "parking": "Parking & Tolls",
    "tolls": "Parking & Tolls",
    "car": "Transportation",
    "driving": "Transportation",
    "car repairs": "Auto Maintenance",
    "commute": "Transportation",
    "flights": "Travel",
    "hotels": "Travel",
    "vacation": "Travel",
    "trips": "Travel",
    "rent": "Rent & Housing",
    "housing": "Rent & Housing",
    "bills": "Utilities",
    "electric": "Utilities",
    "electricity": "Utilities",
    "internet": "Utilities",
    "phone bill": "Utilities",
    "gas bill": "Utilities",
    "medical": "Health",
    "doctor": "Health",
    "pharmacy": "Health",
    "gym": "Health",
    "clothes": "Shopping",
    "amazon": "Shopping",
    "fun": "Entertainment",
    "movies": "Entertainment",
    "streaming": "Subscriptions",
    "bank fees": "Fees",
    "loans": "Loan Payments",
}


class QueryError(ValueError):
    """A bad window or category. Tools turn this into an {"error": ...}
    result the model can recover from, rather than a crash."""

    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.extra = extra


@dataclass(frozen=True)
class Window:
    start: date
    end: date  # inclusive
    name: str  # a NAMED_WINDOWS entry, or "custom"

    @property
    def label(self) -> str:
        return format_range(self.start, self.end)

    def as_dict(self) -> dict:
        return {"window": self.name, "start": self.start.isoformat(), "end": self.end.isoformat(), "label": self.label}


def format_range(start: date, end: date) -> str:
    """"Sep 8–14, 2026", "Aug 28 – Sep 3, 2026", "Dec 29, 2025 – Jan 4, 2026"."""
    if start == end:
        return f"{start:%b} {start.day}, {start.year}"
    if start.year != end.year:
        return f"{start:%b} {start.day}, {start.year} – {end:%b} {end.day}, {end.year}"
    if start.month != end.month:
        return f"{start:%b} {start.day} – {end:%b} {end.day}, {end.year}"
    return f"{start:%b} {start.day}–{end.day}, {end.year}"


# --- "today" -----------------------------------------------------------------


def _now() -> datetime:
    """Isolated so tests can freeze time with one monkeypatch."""
    return datetime.now(timezone.utc)


def user_zone(tz_name: str | None) -> ZoneInfo:
    for name in (tz_name, settings.default_timezone, "UTC"):
        if not name:
            continue
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return ZoneInfo("UTC")


def today_for_user(db: Session, user_id: UUID) -> date:
    user = db.get(User, user_id)
    return _now().astimezone(user_zone(user.timezone if user else None)).date()


# --- windows -----------------------------------------------------------------


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _month_end(d: date) -> date:
    next_month = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def resolve_window(
    today: date, window: str | None = None, start: str | date | None = None, end: str | date | None = None
) -> Window:
    """Explicit start/end win over a named window. Weeks run Monday-Sunday.
    Windows never extend past today (there's no future spending)."""
    if start or end:
        try:
            s = start if isinstance(start, date) else date.fromisoformat(str(start)) if start else None
            e = end if isinstance(end, date) else date.fromisoformat(str(end)) if end else None
        except ValueError as exc:
            raise QueryError("start and end must be YYYY-MM-DD dates") from exc
        e = min(e or today, today)
        if s is None:
            raise QueryError("start is required when giving explicit dates")
        if s > e:
            raise QueryError(f"start ({s}) is after end ({e})")
        return Window(s, e, "custom")

    name = LEGACY_PERIODS.get(window or "", window) or "this_month"
    week_start = today - timedelta(days=today.weekday())
    if name == "today":
        return Window(today, today, name)
    if name == "yesterday":
        y = today - timedelta(days=1)
        return Window(y, y, name)
    if name == "this_week":
        return Window(week_start, today, name)
    if name == "last_week":
        return Window(week_start - timedelta(days=7), week_start - timedelta(days=1), name)
    if name == "this_month":
        return Window(_month_start(today), today, name)
    if name == "last_month":
        last = _month_start(today) - timedelta(days=1)
        return Window(_month_start(last), last, name)
    if name == "this_year":
        return Window(date(today.year, 1, 1), today, name)
    if name == "last_year":
        return Window(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), name)
    if name.startswith("last_") and name.endswith("_days") and name in NAMED_WINDOWS:
        days = int(name.removeprefix("last_").removesuffix("_days"))
        return Window(today - timedelta(days=days - 1), today, name)
    raise QueryError(f"unknown window {window!r}", valid_windows=list(NAMED_WINDOWS))


def same_point_in(previous: Window, current: Window) -> Window:
    """`previous` cut off at the same elapsed point as the in-progress
    `current` -- Sep 1–19 pairs with Aug 1–19, not all of August."""
    elapsed = current.end - current.start
    end = min(previous.start + elapsed, previous.end)
    return Window(previous.start, end, f"{previous.name}_to_date")


# --- categories ---------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedCategory:
    name: str
    ids: tuple[UUID, ...]  # the category itself plus its subcategories
    subcategories: tuple[str, ...]


def resolve_category(db: Session, name: str) -> ResolvedCategory:
    categories = seed_default_categories(db)
    by_lower = {c.lower(): c for c in categories}
    query = name.strip().lower()

    canonical = by_lower.get(query) or CATEGORY_ALIASES.get(query)
    if canonical is None and query.endswith("s"):
        canonical = by_lower.get(query[:-1]) or CATEGORY_ALIASES.get(query[:-1])
    if canonical is None:
        suggestions = get_close_matches(query, [*by_lower, *CATEGORY_ALIASES], n=3, cutoff=0.6)
        raise QueryError(
            f"no category called {name!r}",
            did_you_mean=sorted({by_lower.get(s) or CATEGORY_ALIASES[s] for s in suggestions}),
            valid_categories=spend_category_names(db),
        )

    parent = categories[canonical]
    if parent.type != "expense":
        raise QueryError(
            f"{canonical!r} is not a spending category",
            valid_categories=spend_category_names(db),
        )
    children = [c for c in categories.values() if c.parent_category_id == parent.id]
    return ResolvedCategory(
        name=canonical,
        ids=(parent.id, *(c.id for c in children)),
        subcategories=tuple(sorted(c.name for c in children)),
    )


def spend_category_names(db: Session) -> list[str]:
    return sorted(name for name, c in seed_default_categories(db).items() if c.type == "expense")


# --- queries ------------------------------------------------------------------


def _money(value) -> float:
    return round(float(value or 0), 2)


def _base_query(db: Session, user_id: UUID, window: Window, category_type: str):
    return (
        db.query(Transaction)
        .join(Category, Transaction.bankr_category_id == Category.id)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(
            LinkedAccount.user_id == user_id,
            Category.type == category_type,
            Transaction.date >= window.start,
            Transaction.date <= window.end,
        )
    )


def spend_query(
    db: Session,
    user_id: UUID,
    window: Window,
    category: ResolvedCategory | None = None,
    group_by: str | None = None,
    top_n: int | None = None,
) -> dict:
    """group_by: None | "category" (top-level, subcategories rolled up) |
    "subcategory" (leaf) | "merchant". Groups are sorted biggest first and
    always sum exactly to the total."""
    q = _base_query(db, user_id, window, "expense")
    if category is not None:
        q = q.filter(Transaction.bankr_category_id.in_(category.ids))

    outflow = func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0))
    refunds = func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0))
    pending = func.sum(case((Transaction.is_pending.is_(True), -Transaction.amount), else_=0))
    gross, refunded, pending_amount, count = q.with_entities(
        outflow, refunds, pending, func.count(Transaction.id)
    ).one()

    # Refunds net within their own top-level category, floored at zero: a
    # $500 airline refund offsets travel spending, but must not turn "$50 on
    # Uber" into "-$450 spent". Any excess is reported, not hidden.
    by_top_level = _net_by_key(q, "category")
    total_spent = sum(max(amount, 0) for amount, _ in by_top_level.values())
    excess_refunds = sum(-min(amount, 0) for amount, _ in by_top_level.values())

    result = {
        **window.as_dict(),
        "category": category.name if category else None,
        "total_spent": _money(total_spent),
        "gross_spent": _money(gross),
        "refunds": _money(refunded),
        "pending_amount": _money(pending_amount),
        "transaction_count": int(count),
    }
    if excess_refunds:
        result["refunds_exceeding_spend"] = _money(excess_refunds)
    if category is not None and category.subcategories:
        result["includes_subcategories"] = list(category.subcategories)

    if group_by:
        result["group_by"] = group_by
        result["groups"] = _groups(by_top_level if group_by == "category" else _net_by_key(q, group_by), top_n)
    return result


def _net_by_key(q, group_by: str) -> dict[str, tuple[float, int]]:
    """{group name: (net spent, transaction count)}; refunds count negative."""
    if group_by == "merchant":
        key = func.coalesce(Transaction.merchant_name, "Unknown merchant")
    elif group_by == "category":
        parent = aliased(Category)
        q = q.outerjoin(parent, Category.parent_category_id == parent.id)
        key = func.coalesce(parent.name, Category.name)
    elif group_by == "subcategory":
        key = Category.name
    else:
        raise QueryError("group_by must be one of: category, subcategory, merchant")
    rows = q.with_entities(key, func.sum(-Transaction.amount), func.count(Transaction.id)).group_by(key).all()
    return {name: (float(amount or 0), int(n)) for name, amount, n in rows}


def _groups(nets: dict[str, tuple[float, int]], top_n: int | None) -> list[dict]:
    """Biggest first. Groups that net to a refund are dropped (they're in
    refunds_exceeding_spend), so category groups sum exactly to total_spent."""
    positive = {name: v for name, v in nets.items() if v[0] > 0}
    total = sum(amount for amount, _ in positive.values())
    groups = sorted(
        (
            {
                "name": name,
                "amount": _money(amount),
                "transaction_count": n,
                "share_of_total": round(amount / total, 4) if total else None,
            }
            for name, (amount, n) in positive.items()
        ),
        key=lambda g: g["amount"],
        reverse=True,
    )
    if top_n and len(groups) > top_n:
        rest = groups[top_n:]
        rest_amount = sum(g["amount"] for g in rest)
        groups = groups[:top_n] + [
            {
                "name": f"{len(rest)} others",
                "amount": _money(rest_amount),
                "transaction_count": sum(g["transaction_count"] for g in rest),
                "share_of_total": round(rest_amount / total, 4) if total else None,
            }
        ]
    return groups


def income_query(db: Session, user_id: UUID, window: Window) -> dict:
    q = _base_query(db, user_id, window, "income")
    total, pending_amount, count = q.with_entities(
        func.sum(Transaction.amount),
        func.sum(case((Transaction.is_pending.is_(True), Transaction.amount), else_=0)),
        func.count(Transaction.id),
    ).one()
    return {
        **window.as_dict(),
        "total_income": _money(total),
        "pending_amount": _money(pending_amount),
        "transaction_count": int(count),
    }


def cash_flow(db: Session, user_id: UUID, window: Window) -> dict:
    income = income_query(db, user_id, window)
    spend = spend_query(db, user_id, window)
    return {
        **window.as_dict(),
        "income": income["total_income"],
        "spending": spend["total_spent"],
        "net": _money(income["total_income"] - spend["total_spent"]),
        "income_transaction_count": income["transaction_count"],
        "spending_transaction_count": spend["transaction_count"],
        "pending_spending": spend["pending_amount"],
    }


def compare_spend(
    db: Session,
    user_id: UUID,
    current: Window,
    previous: Window,
    category: ResolvedCategory | None = None,
) -> dict:
    """Difference and percent change are computed here, not by the model."""
    a = spend_query(db, user_id, current, category)
    b = spend_query(db, user_id, previous, category)
    result = {
        "category": category.name if category else None,
        "current": a,
        "previous": b,
        "change": _change(a["total_spent"], b["total_spent"]),
    }
    if _IN_PROGRESS_PREVIOUS.get(current.name) == previous.name and current.end < _period_end(current):
        cut = same_point_in(previous, current)
        b_to_date = spend_query(db, user_id, cut, category)
        result["previous_to_same_point"] = b_to_date
        result["change_vs_same_point"] = _change(a["total_spent"], b_to_date["total_spent"])
        result["note"] = (
            f"{current.label} is still in progress; compare against {cut.label} "
            f"(same point last period) for a fair comparison, and {previous.label} for the full period."
        )
    return result


def _period_end(window: Window) -> date:
    if window.name == "this_month":
        return _month_end(window.start)
    if window.name == "this_week":
        return window.start + timedelta(days=6)
    if window.name == "this_year":
        return date(window.start.year, 12, 31)
    return window.end


def _change(current: float, previous: float) -> dict:
    diff = _money(current - previous)
    return {
        "difference": diff,
        "percent_change": round(diff / previous * 100, 1) if previous else None,
        "direction": "up" if diff > 0 else "down" if diff < 0 else "flat",
    }


def find_transactions(
    db: Session,
    user_id: UUID,
    window: Window,
    category: ResolvedCategory | None = None,
    merchant: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    limit: int = 50,
    category_type: str = "expense",
) -> dict:
    """Spending transactions (outflows and refunds) matching the filters,
    newest first. Amounts: negative = money out, positive = refund.
    min/max compare against the *size* of the charge. category_type="income"
    lists income rows instead (the dashboard's Income drill-down)."""
    q = _base_query(db, user_id, window, category_type)
    if category is not None:
        q = q.filter(Transaction.bankr_category_id.in_(category.ids))
    if merchant:
        q = q.filter(Transaction.merchant_name.ilike(f"%{merchant.strip()}%"))
    if min_amount is not None:
        q = q.filter(func.abs(Transaction.amount) >= min_amount)
    if max_amount is not None:
        q = q.filter(func.abs(Transaction.amount) <= max_amount)

    total_count = q.count()
    rows = (
        q.with_entities(Transaction, Category.name)
        .order_by(Transaction.date.desc(), Transaction.amount)
        .limit(max(1, min(limit, 1000)))
        .all()
    )
    matched_total = q.with_entities(func.sum(-Transaction.amount)).scalar()
    return {
        **window.as_dict(),
        "category": category.name if category else None,
        "merchant": merchant,
        "total_spent": _money(matched_total),
        "transaction_count": total_count,
        "truncated": total_count > len(rows),
        "transactions": [
            {
                "date": txn.date.isoformat(),
                "amount": _money(txn.amount),
                "merchant_name": txn.merchant_name,
                "category": category_name,
                "is_pending": txn.is_pending,
            }
            for txn, category_name in rows
        ],
    }


def data_freshness(db: Session, user_id: UUID) -> str | None:
    """Oldest last-sync across active accounts -- the answer is only as
    fresh as its stalest input."""
    oldest = (
        db.query(func.min(LinkedAccount.last_synced_at))
        .filter(LinkedAccount.user_id == user_id, LinkedAccount.status == "active")
        .scalar()
    )
    return oldest.isoformat() if oldest else None
