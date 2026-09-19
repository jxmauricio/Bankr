"""Read-side queries backing the MVP dashboard.

Deliberately thin: every money figure comes from app/services/money_query.py
(and net worth / goal pace from app/agent/tools.py), the same functions the
chat agent calls, so a tile on the home screen and a chat answer about the
same window can never disagree. This module only adds the list-shaped
views the dashboard UI needs.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.tools import get_net_worth
from app.db.models import NetWorthSnapshot
from app.services import money_query as mq


def _window(db: Session, user_id: UUID, period=None, window=None, start=None, end=None) -> mq.Window:
    return mq.resolve_window(mq.today_for_user(db, user_id), window or period, start, end)


def get_net_worth_history(db: Session, user_id: UUID, limit: int = 90) -> dict:
    snapshots = (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.user_id == user_id)
        .order_by(NetWorthSnapshot.date.desc())
        .limit(limit)
        .all()
    )
    breakdown = get_net_worth(db, user_id)
    current = breakdown.get("net_worth")
    if current is None and snapshots:
        current = float(snapshots[0].net_worth)
    return {
        "current": current,
        "total_assets": breakdown.get("total_assets"),
        "total_liabilities": breakdown.get("total_liabilities"),
        "accounts": breakdown.get("accounts", []),
        "excluded_accounts": breakdown.get("excluded_accounts", []),
        "as_of": breakdown.get("data_as_of"),
        "history": [
            {"date": s.date.isoformat(), "net_worth": float(s.net_worth)}
            for s in reversed(snapshots)
        ],
    }


def get_itemized_transactions(
    db: Session,
    user_id: UUID,
    kind: str,
    period: str | None = "month",
    window: str | None = None,
    start: str | None = None,
    end: str | None = None,
    category: str | None = None,
    merchant: str | None = None,
) -> dict:
    """`kind` is "income" or "expense". For expense, the items include
    refunds (positive amounts) because the total is net of them -- the
    list must visibly add up to the headline figure."""
    w = _window(db, user_id, period, window, start, end)
    resolved_category = mq.resolve_category(db, category) if category and kind == "expense" else None
    listing = mq.find_transactions(
        db, user_id, w, resolved_category, merchant=merchant, limit=1000, category_type=kind
    )
    if kind == "expense":
        total = mq.spend_query(db, user_id, w, resolved_category)["total_spent"] if not merchant else listing["total_spent"]
    else:
        total = mq.income_query(db, user_id, w)["total_income"]
    return {
        "period": period,
        **w.as_dict(),
        "category": resolved_category.name if resolved_category else None,
        "total": total,
        "transaction_count": listing["transaction_count"],
        "items": listing["transactions"],
        "as_of": mq.data_freshness(db, user_id),
    }


def get_period_rollup(db: Session, user_id: UUID, period: str | None = "month", window: str | None = None) -> dict:
    flow = mq.cash_flow(db, user_id, _window(db, user_id, period, window))
    return {
        "period": period,
        "window": flow["window"],
        "start": flow["start"],
        "end": flow["end"],
        "label": flow["label"],
        "income": flow["income"],
        "spending": flow["spending"],
        "gain": flow["net"],
        "pending_spending": flow["pending_spending"],
        "as_of": mq.data_freshness(db, user_id),
    }
