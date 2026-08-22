"""DB-backed implementations of every tool the Claude agent is allowed to call.

Deliberately narrow: each function takes a user_id and returns a small,
already-aggregated JSON-serializable result. The model never sees raw SQL or
a full transaction dump -- this keeps answers grounded, cheap, and auditable,
and structurally prevents the agent from reaching outside banking/spending
data (there is no investment or trade-execution tool to call).
"""

from datetime import date, timedelta
from statistics import mean, pstdev
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Category, Goal, LinkedAccount, NetWorthSnapshot, Transaction

PERIOD_DAYS = {"week": 7, "month": 30, "year": 365}


def get_net_worth(db: Session, user_id: UUID) -> dict:
    snapshot = (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.user_id == user_id)
        .order_by(NetWorthSnapshot.date.desc())
        .first()
    )
    if snapshot is None:
        return {"net_worth": None, "as_of": None, "message": "No net worth snapshot yet."}
    return {
        "net_worth": float(snapshot.net_worth),
        "total_assets": float(snapshot.total_assets),
        "total_liabilities": float(snapshot.total_liabilities),
        "as_of": snapshot.date.isoformat(),
    }


def get_spending_by_category(db: Session, user_id: UUID, period: str = "month") -> dict:
    """Returns positive amounts (money spent), even though expense
    transactions are stored as negative (money out) internally.

    Only sums outflows (amount < 0). Without that filter, a refund tagged
    under an expense category (e.g. an airline refund under Transportation)
    can net a category positive, and abs() of that net would misreport a
    net *gain* as spending -- confirmed against real Plaid sandbox data."""
    since = date.today() - timedelta(days=PERIOD_DAYS.get(period, 30))
    rows = (
        db.query(Category.name, func.sum(Transaction.amount))
        .join(Transaction, Transaction.bankr_category_id == Category.id)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(
            LinkedAccount.user_id == user_id,
            Category.type == "expense",
            Transaction.amount < 0,
            Transaction.date >= since,
        )
        .group_by(Category.name)
        .all()
    )
    return {"period": period, "by_category": {name: abs(float(total)) for name, total in rows}}


def get_income_by_period(db: Session, user_id: UUID, period: str = "month") -> dict:
    since = date.today() - timedelta(days=PERIOD_DAYS.get(period, 30))
    total = (
        db.query(func.sum(Transaction.amount))
        .join(Category, Transaction.bankr_category_id == Category.id)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(
            LinkedAccount.user_id == user_id,
            Category.type == "income",
            Transaction.date >= since,
        )
        .scalar()
    )
    return {"period": period, "total_income": float(total or 0)}


def get_goal_progress(db: Session, user_id: UUID) -> dict:
    goal = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .first()
    )
    if goal is None:
        return {"goal": None, "message": "No active goal set."}

    progress_fraction = float(goal.current_progress_amount) / float(goal.target_amount) if goal.target_amount else 0
    result = {
        "type": goal.type,
        "target_amount": float(goal.target_amount),
        "current_progress_amount": float(goal.current_progress_amount),
        "progress_fraction": round(progress_fraction, 4),
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
    }

    if goal.target_date:
        # days_elapsed is NOT floored to 1 here: a goal created moments ago
        # has 0 days elapsed and should look on-pace, not instantly "behind".
        days_elapsed = max((date.today() - goal.created_at.date()).days, 0)
        days_total = max((goal.target_date - goal.created_at.date()).days, 1)
        expected_fraction = min(days_elapsed / days_total, 1.0)
        result["expected_progress_fraction"] = round(expected_fraction, 4)
        result["on_pace"] = progress_fraction >= expected_fraction

    return result


def get_recent_transactions(db: Session, user_id: UUID, limit: int = 20) -> dict:
    rows = (
        db.query(Transaction, Category.name)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .outerjoin(Category, Transaction.bankr_category_id == Category.id)
        .filter(LinkedAccount.user_id == user_id)
        .order_by(Transaction.date.desc())
        .limit(limit)
        .all()
    )
    return {
        "transactions": [
            {
                "date": txn.date.isoformat(),
                "amount": float(txn.amount),
                "merchant_name": txn.merchant_name,
                "category": category_name,
                "is_pending": txn.is_pending,
            }
            for txn, category_name in rows
        ]
    }


def get_unusual_transactions(db: Session, user_id: UUID, stddev_threshold: float = 2.5) -> dict:
    """Flag recent transactions that are outliers vs. the user's typical transaction size."""
    since = date.today() - timedelta(days=90)
    rows = (
        db.query(Transaction)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(LinkedAccount.user_id == user_id, Transaction.date >= since)
        .all()
    )
    amounts = [float(t.amount) for t in rows]
    if len(amounts) < 5:
        return {"unusual_transactions": [], "message": "Not enough history yet."}

    avg, std = mean(amounts), pstdev(amounts) or 1.0
    recent_since = date.today() - timedelta(days=7)
    unusual = [
        t
        for t in rows
        if t.date >= recent_since and abs(float(t.amount) - avg) > stddev_threshold * std
    ]
    return {
        "unusual_transactions": [
            {"date": t.date.isoformat(), "amount": float(t.amount), "merchant_name": t.merchant_name}
            for t in unusual
        ]
    }
