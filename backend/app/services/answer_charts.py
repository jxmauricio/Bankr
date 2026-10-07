"""The answer-shaped charts behind show_chart's newer kinds -- spending day by
day, one merchant over time, recurring charges, and what moved net worth --
plus the headline every chart answer opens with.

Same contract as the original three kinds in app/agent/tools.py: the model
only says *what* to chart; every number here comes from a fresh query, and
every bar carries the filter (`query`) for the exact rows it's drawn from,
so the chat can list them under the chart.
"""

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import LinkedAccount, NetWorthSnapshot, Transaction
from app.services import money_query as mq
from app.services.recurring_service import recurring_overview
from app.services.sync_service import LIABILITY_ACCOUNT_TYPES

MAX_DAILY_DAYS = 62
MAX_MERCHANT_MONTHS = 12
RECURRING_HISTORY_DAYS = 365
RECURRING_KINDS = {"subscriptions": ("subscription",), "bills": ("bill",), "all": ("subscription", "bill")}


def short_range(start: date, end: date) -> str:
    """"Sep 10–17" -- the year only when it isn't obvious."""
    return mq.format_range(start, end).rsplit(", ", 1)[0]


def headline(eyebrow: str, value: float, detail: str | None = None, tone: str | None = None) -> dict:
    """The answer first: a small label, one big number, one line of context."""
    return {"eyebrow": eyebrow.upper(), "value": mq._money(value), "detail": detail, "tone": tone}


def _query(start: date, end: date, *, category=None, merchant=None, kind=None, account_id=None, recurring_id=None) -> dict:
    query = {"start": start.isoformat(), "end": end.isoformat(), "category": category, "merchant": merchant}
    if kind:
        query["kind"] = kind
    if account_id:
        query["account_id"] = str(account_id)
    if recurring_id:
        query["recurring_id"] = str(recurring_id)
    return query


def _count(n: int, word: str = "transaction") -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# --- spending day by day --------------------------------------------------------


def daily(db: Session, user_id: UUID, window: mq.Window, category: mq.ResolvedCategory | None) -> dict:
    days = (window.end - window.start).days + 1
    if days > MAX_DAILY_DAYS:
        raise mq.QueryError(f"a daily chart covers at most {MAX_DAILY_DAYS} days; use a trend for longer")
    whole = mq.spend_query(db, user_id, window, category)
    cat = whole["category"]
    points = []
    for offset in range(days):
        day = window.start + timedelta(days=offset)
        spent = mq.spend_query(db, user_id, mq.Window(day, day, "custom"), category)
        points.append(
            {
                "label": f"{day:%b} {day.day}",
                "weekday": f"{day:%a}",
                "value": spent["total_spent"],
                "count": spent["transaction_count"],
                "query": _query(day, day, category=cat),
            }
        )
    n = whole["transaction_count"]
    return {
        "kind": "daily",
        "title": f"{cat or 'Spending'} by day",
        "period": short_range(window.start, window.end),
        "points": points,
        "query": _query(window.start, window.end, category=cat),
        "headline": headline(
            f"{short_range(window.start, window.end)} · {_count(days, 'day')}",
            whole["total_spent"],
            f"spent across {_count(n)}",
        ),
        "_count": n,
    }


# --- one merchant over time -----------------------------------------------------


def _month_end(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _month_windows(today: date, months: int) -> list[mq.Window]:
    """The last `months` calendar months, oldest first, the current one to date."""
    windows: list[mq.Window] = []
    cursor = today.replace(day=1)
    while len(windows) < months:
        windows.append(mq.Window(cursor, min(_month_end(cursor), today), "custom"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    windows.reverse()
    return windows


def merchant(db: Session, user_id: UUID, name: str, months: int | None) -> dict:
    name = (name or "").strip()
    if not name:
        raise mq.QueryError("merchant is required for a merchant chart")
    today = mq.today_for_user(db, user_id)
    # Default: this year so far, like "how much on Amazon this year".
    months = max(1, min(int(months or today.month), MAX_MERCHANT_MONTHS))
    windows = _month_windows(today, months)
    whole_window = mq.Window(windows[0].start, today, "custom")
    whole = mq.find_transactions(db, user_id, whole_window, merchant=name, limit=1000)

    points = []
    for w in windows:
        month = mq.find_transactions(db, user_id, w, merchant=name, limit=1)
        points.append(
            {
                "label": f"{w.start:%b}",
                "value": month["total_spent"],
                "count": month["transaction_count"],
                "partial": w.end < _month_end(w.start),
                "query": _query(w.start, w.end, merchant=name),
            }
        )

    charges = [t for t in whole["transactions"] if t["amount"] < 0]
    n = whole["transaction_count"]
    largest = min(charges, key=lambda t: t["amount"], default=None)
    stats = [
        {"label": "Orders", "value": n, "unit": "count"},
        {"label": "Average order", "value": mq._money(whole["total_spent"] / n) if n else 0.0, "unit": "usd"},
    ]
    if largest:
        stats.append({"label": "Largest", "value": abs(largest["amount"]), "unit": "usd", "date": largest["date"]})
    return {
        "kind": "merchant",
        "title": f"{name} by month",
        "period": short_range(whole_window.start, whole_window.end),
        "points": points,
        "average": mq._money(whole["total_spent"] / len(points)) if points else 0.0,
        "stats": stats,
        "query": _query(whole_window.start, whole_window.end, merchant=name),
        "headline": headline(
            f"{name} · {mq.format_range(whole_window.start, whole_window.end)}",
            whole["total_spent"],
            f"over {_count(n, 'order')}",
        ),
        "_count": n,
    }


# --- recurring charges --------------------------------------------------------------


def recurring(db: Session, user_id: UUID, which: str | None, days_ahead: int = 30) -> dict:
    kinds = RECURRING_KINDS.get(which or "subscriptions")
    if kinds is None:
        raise mq.QueryError(f"recurring must be one of: {', '.join(RECURRING_KINDS)}")
    overview = recurring_overview(db, user_id, days_ahead=days_ahead)
    today = date.fromisoformat(overview["today"])
    since = today - timedelta(days=RECURRING_HISTORY_DAYS)
    series = [s for s in overview["series"] if s["kind"] in kinds and s["is_active"]]
    ids = {s["id"] for s in series}
    points = [
        {
            "label": s["name"],
            "value": s["monthly_amount"],
            "next_date": s["next_expected_date"],
            "cadence": s["cadence"],
            "last_amount": s["last_amount"],
            "typical_amount": s["typical_amount"],
            "price_changed": s["price_changed"],
            "suggested": s["status"] == "suggested",
            "query": _query(since, today, kind="all", recurring_id=s["id"]),
        }
        for s in sorted(series, key=lambda s: s["next_expected_date"])
    ]
    upcoming = [
        {"label": u["name"], "date": u["date"], "value": u["amount"]}
        for u in overview["upcoming"]
        if u["series_id"] in ids
    ]
    monthly = sum(p["value"] for p in points)
    noun = {"subscriptions": "subscription", "bills": "bill"}.get(which or "subscriptions", "recurring charge")
    return {
        "kind": "recurring",
        "title": "Next 30 days",
        "period": short_range(today, today + timedelta(days=days_ahead)),
        "today": today.isoformat(),
        "horizon": (today + timedelta(days=days_ahead)).isoformat(),
        "points": points,
        "upcoming": upcoming,
        "query": None,
        "headline": headline(_count(len(points), noun), monthly, _recurring_detail(monthly, points)),
        "_count": len(points),
    }


def _recurring_detail(monthly: float, points: list[dict]) -> str:
    """"a month · $1,529.52 a year", saying when the total includes series
    the user hasn't confirmed are really recurring."""
    detail = f"a month · {_dollars(monthly * 12)} a year"
    suggested = sum(1 for p in points if p["suggested"])
    return f"{detail} · {suggested} not confirmed yet" if suggested else detail


def _dollars(value: float) -> str:
    return f"${value:,.2f}"


# --- what moved net worth -------------------------------------------------------------


def net_worth(db: Session, user_id: UUID, window: mq.Window) -> dict:
    """Each account's change is the sum of its own transactions in the
    window -- the one part of a balance change Bankr can see line by line.
    When there's a net-worth snapshot from the start of the window, what the
    transactions don't explain (market moves, interest, a late sync) is its
    own labelled bar rather than folded into an account."""
    accounts = (
        db.query(LinkedAccount)
        .filter(LinkedAccount.user_id == user_id, LinkedAccount.status == "active")
        .order_by(LinkedAccount.institution_name, LinkedAccount.mask)
        .all()
    )
    if not accounts:
        raise mq.QueryError("no linked accounts")
    flows = dict(
        db.query(Transaction.linked_account_id, func.sum(Transaction.amount))
        .filter(
            Transaction.linked_account_id.in_([a.id for a in accounts]),
            Transaction.date >= window.start,
            Transaction.date <= window.end,
            Transaction.split_parent_id.is_(None),
        )
        .group_by(Transaction.linked_account_id)
        .all()
    )
    points = [
        {
            "label": mq.account_label(a),
            "value": mq._money(flows.get(a.id) or 0),
            "query": _query(window.start, window.end, kind="all", account_id=a.id),
        }
        for a in accounts
    ]
    points = sorted((p for p in points if p["value"]), key=lambda p: -p["value"])
    moved = sum(p["value"] for p in points)

    current = sum(
        float(a.current_balance or 0) * (-1 if a.account_type in LIABILITY_ACCOUNT_TYPES else 1) for a in accounts
    )
    snapshot = (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.user_id == user_id, NetWorthSnapshot.date < window.start)
        .order_by(NetWorthSnapshot.date.desc())
        .first()
    )
    span = f"{window.start:%b} {window.start.day} → {window.end:%b} {window.end.day}"
    if snapshot is not None:
        start_value = float(snapshot.net_worth)
        change = current - start_value
        other = mq._money(change - moved)
        if other:
            points.append({"label": "Not from transactions", "value": other, "query": None, "note": True})
        top = headline(span, change, f"{_dollars(start_value)} → {_dollars(current)}", "pos" if change >= 0 else "neg")
    else:
        top = headline(span, moved, "from transactions; no balance saved from the start", "pos" if moved >= 0 else "neg")
    return {
        "kind": "net_worth",
        "title": "What moved it, by account",
        "period": short_range(window.start, window.end),
        "points": points,
        "query": None,
        "headline": top,
        "_count": len(points),
    }
