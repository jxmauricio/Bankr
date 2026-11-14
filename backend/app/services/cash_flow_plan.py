"""Expected income for a window — including paychecks that haven't landed yet.

"This month" means every payday in the calendar month, not deposits so far.
Money left on Budget is expected pay minus the budget (tracker limits)
minus spending that isn't in any of those budgets — Saved, then minus
everything outside the budget.
"""

import re
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import CashFlowIncome, Category, CategoryGroup, Goal, RecurringSeries, Transaction
from app.services import money_query as mq
from app.services.goal_service import TRACK_SPENDING, tracker_category
from app.services.recurring_service import is_active, merchant_key, next_after, prev_before

INCOME_CADENCES = ("weekly", "biweekly", "monthly", "yearly")
CADENCE_LABEL = {
    "weekly": "weekly",
    "biweekly": "every 2 weeks",
    "monthly": "monthly",
    "quarterly": "quarterly",
    "yearly": "yearly",
}
WINDOW_LABEL = {
    "this_week": "this week",
    "this_month": "this month",
    "this_year": "this year",
    "last_7_days": "the last 7 days",
    "last_30_days": "the last 30 days",
    "last_90_days": "the last 90 days",
}
# Recurring outflows land in these budget groups, vendors nested under each.
_SUBSCRIPTION_KEYS = {"entertainment_and_recreation", "general_shopping", "electronics"}
_SUBSCRIPTION_NAME_HINTS = ("software", "subscription", "entertainment", "streaming", "general services")
_FITNESS_KEYS = {"fitness"}
_FITNESS_NAME_HINTS = ("gym", "fitness", "health club")
_HOUSING_KEYS = {"rent", "mortgage", "housing"}
_HOUSING_NAME_HINTS = ("rent", "mortgage")
_GROUP_ORDER = ("subscriptions", "housing", "bills_and_utilities", "fitness")
_PAYROLL_TAIL = re.compile(r"\s+PAYROLL.*", re.I)


def _short_payer(name: str) -> str:
    """Bank memos like 'Alarm.com-OSV PAYROLL328…' -> 'Alarm.com'."""
    n = _PAYROLL_TAIL.sub("", name).strip(" -")
    head = n.split("-", 1)[0].strip()
    if "." in head:
        return head
    return n or name


def _pretty(n: float) -> str:
    n = mq._money(n)
    return f"${int(n):,}" if n == int(n) else f"${n:,.2f}"


def _income_end(today: date, window: mq.Window) -> date:
    """Last day a paycheck still counts for this window. In-progress
    calendars run through the end of the week/month/year, not today."""
    if window.name == "this_month":
        return mq._month_end(today)
    if window.name == "this_week":
        return today - timedelta(days=today.weekday()) + timedelta(days=6)
    if window.name == "this_year":
        return date(today.year, 12, 31)
    return window.end


def dates_in_range(anchor: date, cadence: str, start: date, end: date) -> list[date]:
    """Paydays of a series whose last pay was `anchor`, inside [start, end]."""
    found: set[date] = set()
    d = anchor
    for _ in range(400):
        if d < start:
            break
        if d <= end:
            found.add(d)
        d = prev_before(d, cadence)
    d = next_after(anchor, cadence)
    for _ in range(400):
        if d > end:
            break
        if d >= start:
            found.add(d)
        d = next_after(d, cadence)
    return sorted(found)


def dates_from_start(cadence: str, start: date, end: date) -> list[date]:
    """Custom income with no payday history: first on `start`, then the cadence."""
    found: list[date] = []
    d = start
    for _ in range(400):
        if d > end:
            break
        found.append(d)
        d = next_after(d, cadence)
    return found


def _detected_income(db: Session, user_id: UUID, window: mq.Window, today: date) -> list[dict]:
    series = (
        db.query(RecurringSeries)
        .filter(
            RecurringSeries.user_id == user_id,
            RecurringSeries.status != "dismissed",
            RecurringSeries.kind == "income",
        )
        .all()
    )
    # Confirmed paychecks stay on the plan even if detection's next-date
    # is a cycle behind — November still has two Alarm.com Fridays.
    active = [s for s in series if s.status == "confirmed" or is_active(s, today)]
    horizon = _income_end(today, window)
    if active:
        out = []
        for s in active:
            days = dates_in_range(s.last_date, s.cadence, window.start, horizon)
            out.append(
                {
                    "origin": "detected",
                    "series_id": str(s.id),
                    "payer": s.display_name,
                    "name": _short_payer(s.display_name),
                    "amount": mq._money(s.last_amount),
                    "cadence": s.cadence,
                    "last_date": s.last_date.isoformat(),
                    "dates": [d.isoformat() for d in days],
                }
            )
        return out
    flow = mq.cash_flow_breakdown(db, user_id, window)
    return [
        {
            "origin": "detected",
            "series_id": None,
            "payer": src["name"],
            "name": src["name"],
            "amount": src["amount"],
            "cadence": "monthly",
            "last_date": window.start.isoformat(),
            "dates": [window.start.isoformat()],
        }
        for src in flow["sources"]
        if src["amount"] > 0
    ]


def _name_matches(name: str, hints: tuple[str, ...]) -> bool:
    lower = name.lower()
    return any(h in lower for h in hints)


def _series_budget_group(series: RecurringSeries, category: Category | None, group: CategoryGroup | None) -> tuple[str, str, str | None]:
    """(key, label, track-new category name or None). Subscriptions and gyms
    collect their vendors; other bills stay under their real category."""
    cat_key = category.system_key if category else None
    group_key = group.system_key if group else None
    cat_name = category.name if category else ""
    group_name = group.name if group else ""
    if series.kind == "subscription" or cat_key in _SUBSCRIPTION_KEYS or _name_matches(cat_name, _SUBSCRIPTION_NAME_HINTS):
        return "subscriptions", "Subscriptions", None
    if cat_key in _FITNESS_KEYS or _name_matches(cat_name, _FITNESS_NAME_HINTS) or _name_matches(group_name, _FITNESS_NAME_HINTS):
        return "fitness", "Fitness", "Fitness"
    if cat_key in _HOUSING_KEYS or group_key == "housing" or _name_matches(cat_name, _HOUSING_NAME_HINTS):
        return "housing", group_name or "Housing", group_name or "Housing"
    if group_key == "bills_and_utilities":
        return group_key, group_name, group_name
    if category is not None:
        return cat_key or str(category.id), cat_name, cat_name
    return "other_recurring", "Other", None


def recurring_budget_groups(db: Session, user_id: UUID, window_name: str = "this_month") -> list[dict]:
    """Recurring outflows for Budget: grouped (Subscriptions, Fitness, Housing,
    …) with each vendor nested, expected for the window, spent so far."""
    today = mq.today_for_user(db, user_id)
    window = mq.resolve_window(today, window_name)
    horizon = _income_end(today, window)
    rows = (
        db.query(RecurringSeries)
        .filter(
            RecurringSeries.user_id == user_id,
            RecurringSeries.direction == "out",
            RecurringSeries.status != "dismissed",
            RecurringSeries.in_budget.is_(True),
            RecurringSeries.kind != "income",
        )
        .all()
    )
    trackers = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active", Goal.type == TRACK_SPENDING)
        .all()
    )
    merchant_goals: dict[str, Goal] = {}
    for g in trackers:
        if not g.merchant or (g.window or "this_month") != window_name:
            continue
        merchant_goals[(g.merchant or "").strip().lower()] = g
        merchant_goals[merchant_key(g.merchant)] = g
    category_goals = {
        (g.name or "").strip().lower(): g
        for g in trackers
        if not g.merchant and (g.window or "this_month") == window_name
    }
    for g in trackers:
        if g.merchant or (g.window or "this_month") != window_name:
            continue
        try:
            resolved = tracker_category(db, user_id, g)
        except mq.QueryError:
            continue
        if resolved is not None:
            category_goals.setdefault(resolved.name.lower(), g)
            category_goals.setdefault(resolved.top_level.lower(), g)

    buckets: dict[str, dict] = {}
    for series in rows:
        posted = window.start <= series.last_date <= window.end
        active = is_active(series, today)
        if not active and not posted:
            continue
        category = db.get(Category, series.category_id) if series.category_id else None
        group = db.get(CategoryGroup, category.group_id) if category and category.group_id else None
        key, label, open_as = _series_budget_group(series, category, group)
        days = dates_in_range(series.last_date, series.cadence, window.start, horizon) if active else [series.last_date]
        expected = mq._money(float(series.last_amount) * len(days))
        spend = mq.spend_query(db, user_id, window, merchant=series.display_name, group_by="category")
        spent = spend["total_spent"]
        spend_group = spend["groups"][0]["name"] if spend.get("groups") else (group.name if group else None)
        goal = merchant_goals.get(series.display_name.strip().lower()) or merchant_goals.get(series.merchant_key)
        limit = float(goal.target_amount) if goal is not None and float(goal.target_amount or 0) > 0 else expected
        vendor = {
            "series_id": str(series.id),
            "name": series.display_name,
            "merchant": series.display_name,
            "expected": expected,
            "spent": spent,
            "limit": mq._money(limit),
            "cadence": series.cadence,
            "kind": series.kind,
            "status": series.status,
            "spend_group": spend_group,
            "goal_id": str(goal.id) if goal is not None else None,
        }
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {"key": key, "name": label, "open_as": open_as, "vendors": []}
            buckets[key] = bucket
        bucket["vendors"].append(vendor)

    groups = []
    for key, bucket in buckets.items():
        vendors = sorted(bucket["vendors"], key=lambda v: v["limit"], reverse=True)
        goal = category_goals.get(bucket["name"].lower())
        groups.append(
            {
                "key": bucket["key"],
                "name": bucket["name"],
                "open_as": bucket["open_as"],
                "expected": mq._money(sum(v["expected"] for v in vendors)),
                "spent": mq._money(sum(v["spent"] for v in vendors)),
                "limit": mq._money(sum(v["limit"] for v in vendors)),
                "goal_id": str(goal.id) if goal is not None else None,
                "vendors": vendors,
            }
        )
    groups.sort(key=lambda g: (_GROUP_ORDER.index(g["key"]) if g["key"] in _GROUP_ORDER else 99, -g["limit"], g["name"]))
    return groups


def money_left_plan(db: Session, user_id: UUID, window_name: str = "this_month") -> dict:
    today = mq.today_for_user(db, user_id)
    window = mq.resolve_window(today, window_name)
    horizon = _income_end(today, window)
    spent = mq.spend_query(db, user_id, window)["total_spent"]
    saved = db.query(CashFlowIncome).filter(CashFlowIncome.user_id == user_id).all()
    by_series = {str(r.series_id): r for r in saved if r.series_id is not None}
    by_payer = {r.payer: r for r in saved if r.series_id is None and r.payer}
    custom = [r for r in saved if r.series_id is None and not r.payer]

    incomes = []
    for src in _detected_income(db, user_id, window, today):
        row = by_series.get(src["series_id"] or "") or by_payer.get(src["payer"])
        cadence = row.cadence if row is not None else src["cadence"]
        amount = float(row.amount) if row is not None else src["amount"]
        included = bool(row.included) if row is not None else True
        anchor = date.fromisoformat(src["last_date"]) if src.get("last_date") else window.start
        days = dates_in_range(anchor, cadence, window.start, horizon)
        n = len(days)
        window_amount = mq._money(amount * n)
        when = WINDOW_LABEL.get(window.name, window.label.lower())
        cadence_label = CADENCE_LABEL.get(cadence, cadence)
        note = f"{n}× {when} · {cadence_label} · {_pretty(amount)} each" if n else f"none {when} · {cadence_label}"
        incomes.append(
            {
                "id": str(row.id) if row is not None else None,
                "origin": "detected",
                "series_id": src["series_id"],
                "payer": src["payer"],
                "name": row.name if row is not None else src["name"],
                "amount": mq._money(amount),
                "cadence": cadence,
                "occurrences": n,
                "dates": [d.isoformat() for d in days],
                "monthly_amount": window_amount,
                "window_amount": window_amount,
                "included": included,
                "note": note,
            }
        )
    for row in custom:
        cadence = row.cadence
        days = dates_from_start(cadence, window.start, horizon)
        n = len(days)
        amount = float(row.amount)
        window_amount = mq._money(amount * n)
        when = WINDOW_LABEL.get(window.name, window.label.lower())
        cadence_label = CADENCE_LABEL.get(cadence, cadence)
        incomes.append(
            {
                "id": str(row.id),
                "origin": "custom",
                "series_id": None,
                "payer": None,
                "name": row.name,
                "amount": mq._money(amount),
                "cadence": cadence,
                "occurrences": n,
                "dates": [d.isoformat() for d in days],
                "monthly_amount": window_amount,
                "window_amount": window_amount,
                "included": bool(row.included),
                "note": f"{n}× {when} · {cadence_label} · {_pretty(amount)} each",
            }
        )

    income_total = mq._money(sum(i["window_amount"] for i in incomes if i["included"]))
    recurring_groups = recurring_budget_groups(db, user_id, window_name)
    budgeted, unbudgeted = _budget_and_outside(db, user_id, window, window_name, recurring_groups)
    left = mq._money(income_total - budgeted - unbudgeted)

    return {
        **window.as_dict(),
        "income_end": horizon.isoformat(),
        "incomes": incomes,
        "income_total": income_total,
        "spent": mq._money(spent),
        "budgeted": budgeted,
        "unbudgeted_spent": unbudgeted,
        "recurring_groups": recurring_groups,
        "upcoming": [],
        "upcoming_total": 0,
        "savings": [],
        "savings_total": 0,
        "left": left,
        "as_of": mq.data_freshness(db, user_id),
    }


def _budget_and_outside(
    db: Session,
    user_id: UUID,
    window: mq.Window,
    window_name: str,
    recurring_groups: list[dict] | None = None,
) -> tuple[float, float]:
    """Recurring vendor limits plus tracker limits that don't overlap them,
    and expense spend those budgets don't cover."""
    groups = recurring_groups if recurring_groups is not None else recurring_budget_groups(db, user_id, window_name)
    budgeted = sum(g["limit"] for g in groups)
    merchants = [v["merchant"] for g in groups for v in g["vendors"] if v["merchant"]]
    recurring_keys = {merchant_key(m) for m in merchants}
    group_names = {g["name"].lower() for g in groups} | {g["key"] for g in groups}
    category_ids: set[UUID] = set()

    trackers = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active", Goal.type == TRACK_SPENDING)
        .all()
    )
    for goal in trackers:
        if (goal.window or "this_month") != window_name:
            continue
        limit = float(goal.target_amount or 0)
        if limit <= 0:
            continue
        if goal.merchant:
            if merchant_key(goal.merchant) in recurring_keys:
                continue
            budgeted += limit
            merchants.append(goal.merchant.strip())
            continue
        try:
            resolved = tracker_category(db, user_id, goal)
        except mq.QueryError:
            continue
        if resolved is None:
            continue
        if resolved.name.lower() in group_names or resolved.top_level.lower() in group_names:
            continue
        budgeted += limit
        category_ids.update(resolved.ids)

    q = mq._base_query(db, user_id, window, "expense")
    covered = []
    if category_ids:
        covered.append(Transaction.category_id.in_(list(category_ids)))
    if merchants:
        covered.append(or_(*[Transaction.merchant_name.ilike(f"%{m}%") for m in merchants]))
    if covered:
        q = q.filter(~or_(*covered))
    by_top = mq._net_by_key(q, "category", user_id)
    unbudgeted = sum(max(amount, 0) for amount, _, _ in by_top.values())
    return mq._money(budgeted), mq._money(unbudgeted)


def upsert_income(
    db: Session,
    user_id: UUID,
    *,
    income_id: UUID | None = None,
    series_id: UUID | None = None,
    payer: str | None = None,
    name: str,
    amount: float,
    cadence: str = "monthly",
    included: bool = True,
) -> CashFlowIncome:
    if cadence not in INCOME_CADENCES:
        raise mq.QueryError(f"cadence must be one of {list(INCOME_CADENCES)}")
    if amount < 0 or not (amount < 1_000_000_000):
        raise mq.QueryError("amount must be $0 or more")
    label = name.strip()[:80] or "Income"
    row = None
    if income_id is not None:
        row = db.query(CashFlowIncome).filter(CashFlowIncome.id == income_id, CashFlowIncome.user_id == user_id).one_or_none()
        if row is None:
            raise mq.QueryError("that income source is gone")
    elif series_id is not None:
        row = db.query(CashFlowIncome).filter(CashFlowIncome.user_id == user_id, CashFlowIncome.series_id == series_id).one_or_none()
    elif payer:
        row = (
            db.query(CashFlowIncome)
            .filter(CashFlowIncome.user_id == user_id, CashFlowIncome.payer == payer, CashFlowIncome.series_id.is_(None))
            .one_or_none()
        )
    if row is None:
        row = CashFlowIncome(user_id=user_id, series_id=series_id, payer=payer)
        db.add(row)
    row.name = label
    row.amount = mq._money(amount)
    row.cadence = cadence
    row.included = included
    if series_id is not None:
        row.series_id = series_id
    if payer:
        row.payer = payer
    db.commit()
    db.refresh(row)
    return row


def delete_income(db: Session, user_id: UUID, income_id: UUID) -> None:
    row = db.query(CashFlowIncome).filter(CashFlowIncome.id == income_id, CashFlowIncome.user_id == user_id).one_or_none()
    if row is None:
        raise mq.QueryError("that income source is gone")
    db.delete(row)
    db.commit()
