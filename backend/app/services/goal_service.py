"""Goal creation and progress recomputation.

Progress is recomputed here, once, right after each sync produces a fresh
NetWorthSnapshot (see sync_service.sync_user_accounts) -- never computed
ad hoc elsewhere, so the dashboard and the chat agent's get_goal_progress
tool (app/agent/tools.py) always agree, per the plan's "one shared backend
function" rule for goal pacing.
"""

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Goal, NetWorthSnapshot

GOAL_TYPES = {"save_amount", "pay_off_debt", "build_emergency_fund"}


def _latest_snapshot(db: Session, user_id: UUID) -> NetWorthSnapshot | None:
    return (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.user_id == user_id)
        .order_by(NetWorthSnapshot.date.desc())
        .first()
    )


def create_goal(
    db: Session,
    user_id: UUID,
    goal_type: str,
    target_amount: float,
    target_date: date | None,
) -> Goal:
    snapshot = _latest_snapshot(db, user_id)
    if goal_type == "pay_off_debt":
        starting_amount = float(snapshot.total_liabilities) if snapshot else 0.0
    else:
        starting_amount = float(snapshot.total_assets) if snapshot else 0.0

    # Any previously active goal is superseded -- Bankr tracks a single goal
    # per user for the MVP (see plan: "help work toward that goal").
    db.query(Goal).filter(Goal.user_id == user_id, Goal.status == "active").update(
        {"status": "abandoned"}
    )

    goal = Goal(
        user_id=user_id,
        type=goal_type,
        target_amount=target_amount,
        target_date=target_date,
        starting_amount=starting_amount,
        current_progress_amount=0,
        status="active",
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def recompute_goal_progress(db: Session, user_id: UUID, snapshot: NetWorthSnapshot) -> None:
    goal = db.query(Goal).filter(Goal.user_id == user_id, Goal.status == "active").one_or_none()
    if goal is None:
        return

    if goal.type == "pay_off_debt":
        goal.current_progress_amount = float(goal.starting_amount) - float(snapshot.total_liabilities)
    else:
        goal.current_progress_amount = float(snapshot.total_assets) - float(goal.starting_amount)

    if goal.target_amount and float(goal.current_progress_amount) >= float(goal.target_amount):
        goal.status = "completed"
