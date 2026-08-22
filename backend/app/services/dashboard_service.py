"""Read-side queries backing the MVP dashboard.

Deliberately thin: net worth and goal-pace math live in app/agent/tools.py
so the dashboard and the chat agent can never drift apart (see
get_goal_progress in particular, per the plan's "one shared backend
function" rule) -- this module only adds the itemized/list-shaped views the
agent's tools don't need but the dashboard UI does.
"""

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.tools import PERIOD_DAYS, get_income_by_period, get_spending_by_category
from app.db.models import Category, LinkedAccount, NetWorthSnapshot, Transaction


def get_net_worth_history(db: Session, user_id: UUID, limit: int = 90) -> dict:
    snapshots = (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.user_id == user_id)
        .order_by(NetWorthSnapshot.date.desc())
        .limit(limit)
        .all()
    )
    return {
        "current": float(snapshots[0].net_worth) if snapshots else None,
        "history": [
            {"date": s.date.isoformat(), "net_worth": float(s.net_worth)}
            for s in reversed(snapshots)
        ],
    }


def get_itemized_transactions(db: Session, user_id: UUID, kind: str, period: str = "month") -> dict:
    """`kind` is "income" or "expense"; matches Category.type.

    Also filters by amount sign matching `kind` (expense -> outflow only,
    income -> inflow only). Category alone isn't enough: a refund tagged
    under an expense category (e.g. an airline refund under Transportation)
    is a positive-amount transaction that would otherwise show up inside
    the "Spending" list itself -- confirmed against real Plaid sandbox data,
    same root cause as the fix in app/agent/tools.py get_spending_by_category."""
    since = date.today() - timedelta(days=PERIOD_DAYS.get(period, 30))
    sign_filter = Transaction.amount < 0 if kind == "expense" else Transaction.amount > 0
    rows = (
        db.query(Transaction, Category.name)
        .join(Category, Transaction.bankr_category_id == Category.id)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(
            LinkedAccount.user_id == user_id,
            Category.type == kind,
            sign_filter,
            Transaction.date >= since,
        )
        .order_by(Transaction.date.desc())
        .all()
    )
    items = [
        {
            "date": txn.date.isoformat(),
            "amount": float(txn.amount),
            "merchant_name": txn.merchant_name,
            "category": category_name,
            "is_pending": txn.is_pending,
        }
        for txn, category_name in rows
    ]
    total = sum(i["amount"] for i in items)
    return {"period": period, "total": round(abs(total) if kind == "expense" else total, 2), "items": items}


def get_period_rollup(db: Session, user_id: UUID, period: str = "month") -> dict:
    income = get_income_by_period(db, user_id, period)["total_income"]
    spending = sum(get_spending_by_category(db, user_id, period)["by_category"].values())
    return {
        "period": period,
        "income": round(income, 2),
        "spending": round(spending, 2),
        "gain": round(income - spending, 2),
    }
