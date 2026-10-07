"""Finds bills, subscriptions and paychecks that repeat on a schedule.

Runs after every sync. Deterministic, no LLM: transactions are grouped by a
normalized merchant name and direction (money out / in), and a group is
recurring when the gaps between charges sit close to one cadence and the
amounts are steady. New series start as "suggested" for the user to confirm
or dismiss; re-detection refreshes amounts and dates but never overrides
the user's status or kind.
"""

import calendar
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median, pstdev
from uuid import UUID

from sqlalchemy.orm import Session, aliased

from app.db.models import Category, LinkedAccount, RecurringSeries, Transaction
from app.services import money_query as mq

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 400

# cadence -> (typical gap in days, tolerance in days, occurrences per month)
CADENCES: dict[str, tuple[int, int, float]] = {
    "weekly": (7, 2, 52 / 12),
    "biweekly": (14, 3, 26 / 12),
    "monthly": (30, 5, 1.0),
    "quarterly": (91, 10, 1 / 3),
    "yearly": (365, 15, 1 / 12),
}
# How much charge sizes may vary (std dev / mean). Utility bills move with
# usage, so they get more room than a subscription price does.
MAX_VARIATION = 0.25
MAX_VARIATION_UTILITIES = 0.6
PRICE_CHANGE_THRESHOLD = 0.05

SUBSCRIPTION_CATEGORIES = {"Subscriptions", "Entertainment"}
UTILITY_CATEGORIES = {"Utilities"}

_NOISE = re.compile(r"[^a-z ]+")


def merchant_key(name: str | None) -> str:
    """"NETFLIX.COM 866-579" and "Netflix" -> "netflix": letters only, the
    first three words, so store numbers and reference codes don't split one
    merchant into many."""
    words = _NOISE.sub(" ", (name or "").lower()).split()
    words = [w for w in words if w not in {"com", "www", "inc", "llc", "the"}]
    return " ".join(words[:3])


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def next_after(last: date, cadence: str) -> date:
    if cadence == "monthly":
        return add_months(last, 1)
    if cadence == "quarterly":
        return add_months(last, 3)
    if cadence == "yearly":
        return add_months(last, 12)
    return last + timedelta(days=CADENCES[cadence][0])


def is_active(series: RecurringSeries, today: date) -> bool:
    """Still expected: the next charge isn't more than one full cycle late."""
    gap, tolerance, _ = CADENCES[series.cadence]
    return (today - series.next_expected_date).days <= gap + tolerance


def monthly_amount(series: RecurringSeries) -> float:
    return float(series.last_amount) * CADENCES[series.cadence][2]


@dataclass
class _Charge:
    date: date
    amount: float  # positive size
    name: str
    category_id: UUID | None
    category: str | None


def _match_cadence(gaps: list[int]) -> str | None:
    typical = median(gaps)
    for name, (days, tolerance, _) in CADENCES.items():
        if abs(typical - days) <= tolerance:
            # Most gaps (not just the median) must fit, so a merchant you
            # visit "about monthly" by chance doesn't count.
            fitting = sum(1 for g in gaps if abs(g - days) <= tolerance * 1.5)
            if fitting >= max(1, round(len(gaps) * 0.7)):
                return name
    return None


def _detect_group(charges: list[_Charge], direction: str) -> dict | None:
    # Same-day duplicates (a split, a retry) are one occurrence.
    by_day: dict[date, _Charge] = {}
    for c in sorted(charges, key=lambda c: c.date):
        if c.date in by_day:
            by_day[c.date].amount += c.amount
        else:
            by_day[c.date] = _Charge(c.date, c.amount, c.name, c.category_id, c.category)
    series = list(by_day.values())
    if len(series) < 2:
        return None
    gaps = [(b.date - a.date).days for a, b in zip(series, series[1:])]
    cadence = _match_cadence(gaps)
    if cadence is None or len(series) < (2 if cadence == "yearly" else 3):
        return None

    amounts = [c.amount for c in series]
    latest = series[-1]
    limit = MAX_VARIATION_UTILITIES if latest.category in UTILITY_CATEGORIES else MAX_VARIATION
    # Judge steadiness on the history before the latest charge, so a single
    # price increase is reported as a change rather than hiding the series.
    history = amounts[:-1] if len(amounts) > 2 else amounts
    if mean(history) == 0 or pstdev(history) / mean(history) > limit:
        return None

    if direction == "in":
        kind = "income"
    elif latest.category in SUBSCRIPTION_CATEGORIES:
        kind = "subscription"
    else:
        kind = "bill"
    return {
        "display_name": latest.name,
        "category_id": latest.category_id,
        "kind": kind,
        "cadence": cadence,
        "typical_amount": round(median(history), 2),
        "last_amount": round(latest.amount, 2),
        "last_date": latest.date,
        "next_expected_date": next_after(latest.date, cadence),
        "occurrences": len(series),
    }


def _charges(db: Session, user_id: UUID, since: date) -> dict[tuple[str, str], list[_Charge]]:
    parent = aliased(Category)
    rows = (
        db.query(Transaction, Category.name, Category.type, parent.name)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .join(Category, Transaction.bankr_category_id == Category.id)
        .outerjoin(parent, Category.parent_category_id == parent.id)
        .filter(
            LinkedAccount.user_id == user_id,
            Transaction.date >= since,
            Transaction.is_pending.is_(False),
            Category.type != "transfer",
            *mq.counted_filters(),
        )
        .all()
    )
    groups: dict[tuple[str, str], list[_Charge]] = {}
    for txn, name, ctype, parent_name in rows:
        amount = float(txn.amount)
        direction = "in" if amount > 0 else "out"
        if (direction == "in") != (ctype == "income"):
            continue  # refunds and reversals aren't a schedule
        key = merchant_key(txn.merchant_name)
        if not key:
            continue
        groups.setdefault((key, direction), []).append(
            _Charge(txn.date, abs(amount), txn.merchant_name or key, txn.bankr_category_id, parent_name or name)
        )
    return groups


def series_charges(db: Session, user_id: UUID, series_id: UUID, window: mq.Window) -> dict:
    """The past payments a recurring series was detected from -- the
    transactions behind a subscription row in a chat answer. Same matching
    as detection: the normalized merchant name and the money's direction."""
    series = (
        db.query(RecurringSeries)
        .filter(RecurringSeries.id == series_id, RecurringSeries.user_id == user_id)
        .one_or_none()
    )
    if series is None:
        raise mq.QueryError("no such recurring series")
    listing = mq.list_transactions(db, user_id, window)
    rows = [
        row
        for row in listing["transactions"]
        if merchant_key(row["merchant_name"]) == series.merchant_key
        and (row["amount"] > 0) == (series.direction == "in")
    ]
    return {**listing, "transaction_count": len(rows), "truncated": False, "transactions": rows}


def detect_recurring(db: Session, user_id: UUID) -> list[RecurringSeries]:
    """Find or refresh every recurring series for the user. Returns the
    series touched by this run."""
    today = mq.today_for_user(db, user_id)
    existing = {
        (s.merchant_key, s.direction): s
        for s in db.query(RecurringSeries).filter(RecurringSeries.user_id == user_id)
    }
    touched = []
    for (key, direction), charges in _charges(db, user_id, today - timedelta(days=LOOKBACK_DAYS)).items():
        found = _detect_group(charges, direction)
        if found is None:
            continue
        series = existing.get((key, direction))
        if series is None:
            series = RecurringSeries(user_id=user_id, merchant_key=key, direction=direction, status="suggested")
            db.add(series)
        else:
            # The user's choices stand; only the observed numbers refresh.
            found.pop("kind")
            found.pop("display_name")
        for field, value in found.items():
            setattr(series, field, value)
        series.updated_at = datetime.now(timezone.utc)
        touched.append(series)
    db.commit()
    return touched


def detect_recurring_safely(db: Session, user_id: UUID) -> None:
    """detect_recurring, never failing whatever triggered it (a sync response
    or a webhook)."""
    try:
        detect_recurring(db, user_id)
    except Exception:
        db.rollback()
        logger.exception("Recurring detection failed for user %s", user_id)


def price_changes(db: Session, user_id: UUID) -> list[RecurringSeries]:
    """Confirmed subscriptions whose latest charge moved more than
    PRICE_CHANGE_THRESHOLD from what it usually is. Bills are left out:
    utilities move with usage every month, so a change isn't news."""
    return [
        s
        for s in db.query(RecurringSeries).filter(
            RecurringSeries.user_id == user_id,
            RecurringSeries.status == "confirmed",
            RecurringSeries.kind == "subscription",
        )
        if float(s.typical_amount)
        and abs(float(s.last_amount) - float(s.typical_amount)) / float(s.typical_amount) > PRICE_CHANGE_THRESHOLD
    ]


def recurring_merchant_keys(db: Session, user_id: UUID) -> set[str]:
    """Merchants with a non-dismissed recurring series: their charges are
    expected, however large."""
    return {
        key
        for (key,) in db.query(RecurringSeries.merchant_key).filter(
            RecurringSeries.user_id == user_id, RecurringSeries.status != "dismissed"
        )
    }


def series_dict(s: RecurringSeries, today: date) -> dict:
    return {
        "id": str(s.id),
        "name": s.display_name,
        "kind": s.kind,
        "cadence": s.cadence,
        "status": s.status,
        "category_id": str(s.category_id) if s.category_id else None,
        "typical_amount": mq._money(s.typical_amount),
        "last_amount": mq._money(s.last_amount),
        "last_date": s.last_date.isoformat(),
        "next_expected_date": s.next_expected_date.isoformat(),
        "monthly_amount": mq._money(monthly_amount(s)),
        "occurrences": s.occurrences,
        "is_active": is_active(s, today),
        "price_changed": s.kind == "subscription"
        and abs(float(s.last_amount) - float(s.typical_amount)) > PRICE_CHANGE_THRESHOLD * float(s.typical_amount),
    }


def recurring_overview(db: Session, user_id: UUID, days_ahead: int = 30) -> dict:
    """Every non-dismissed series, the charges expected in the next
    `days_ahead` days, and monthly totals of confirmed series."""
    today = mq.today_for_user(db, user_id)
    rows = (
        db.query(RecurringSeries)
        .filter(RecurringSeries.user_id == user_id, RecurringSeries.status != "dismissed")
        .order_by(RecurringSeries.next_expected_date)
        .all()
    )
    horizon = today + timedelta(days=days_ahead)
    upcoming = []
    for s in rows:
        if not is_active(s, today):
            continue
        due = s.next_expected_date
        # A charge that's a few days late is still coming; show it as due today.
        while due <= horizon:
            upcoming.append(
                {
                    "series_id": str(s.id),
                    "name": s.display_name,
                    "kind": s.kind,
                    "status": s.status,
                    "date": max(due, today).isoformat(),
                    "amount": mq._money(s.last_amount),
                }
            )
            due = next_after(due, s.cadence)
    upcoming.sort(key=lambda u: (u["date"], u["name"]))

    confirmed = [s for s in rows if s.status == "confirmed" and is_active(s, today)]

    def total(kind: str) -> float:
        return mq._money(sum(monthly_amount(s) for s in confirmed if s.kind == kind))

    return {
        "today": today.isoformat(),
        "series": [series_dict(s, today) for s in rows],
        "upcoming": upcoming,
        "monthly": {"subscriptions": total("subscription"), "bills": total("bill"), "income": total("income")},
        "suggested_count": sum(1 for s in rows if s.status == "suggested" and is_active(s, today)),
    }
