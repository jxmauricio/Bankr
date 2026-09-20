"""Goal creation and progress recomputation.

Progress is recomputed here, once, right after each sync produces a fresh
NetWorthSnapshot (see sync_service.sync_user_accounts) -- never computed
ad hoc elsewhere, so the dashboard and the chat agent's get_goal_progress
tool (app/agent/tools.py) always agree, per the plan's "one shared backend
function" rule for goal pacing.

Spending trackers (type=track_spending) are the exception to the snapshot
rule: their current_progress_amount is this window's category spend from
money_query, not net-worth movement. get_goal_progress also reads spend
live so the left-rail number stays current between syncs.
"""

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Goal, NetWorthSnapshot
from app.services import money_query as mq

SAVE = "save"
TRACK_SPENDING = "track_spending"
GOAL_TYPES = {SAVE, TRACK_SPENDING}
# Older clients/tests may still send these; they become save + a default name.
LEGACY_SAVE_NAMES = {
    "save_amount": "Savings goals",
    "pay_off_debt": "Paying off debt",
    "build_emergency_fund": "Emergency fund",
}
ACCEPTED_GOAL_TYPES = GOAL_TYPES | set(LEGACY_SAVE_NAMES)
DEFAULT_SAVE_NAME = "Savings"
MAX_ACTIVE_GOALS = 5

# Rolling windows that make sense as a live tracker. Past-only windows
# (last_month, yesterday) are excluded -- those periods are already over.
TRACKING_WINDOWS = (
    "this_week",
    "this_month",
    "this_year",
    "last_7_days",
    "last_30_days",
    "last_90_days",
)
TRACKING_WINDOW_LABELS = {
    "this_week": "This week",
    "this_month": "This month",
    "this_year": "This year",
    "last_7_days": "Last 7 days",
    "last_30_days": "Last 30 days",
    "last_90_days": "Last 90 days",
}
DEFAULT_TRACKING_WINDOW = "this_month"


class GoalLimitReached(Exception):
    """User already has MAX_ACTIVE_GOALS active goals."""


class GoalValidationError(Exception):
    """Bad type/category/window/amount for a goal."""

    def __init__(self, message: str, extra: dict | None = None):
        super().__init__(message)
        self.extra = extra or {}


class GoalNotFound(Exception):
    """No matching active goal for this user."""


def _latest_snapshot(db: Session, user_id: UUID) -> NetWorthSnapshot | None:
    return (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.user_id == user_id)
        .order_by(NetWorthSnapshot.date.desc())
        .first()
    )


def list_active_goals(db: Session, user_id: UUID) -> list[Goal]:
    return (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active")
        .order_by(Goal.created_at.asc())
        .all()
    )


def spend_for_tracker(db: Session, user_id: UUID, category: str, window_name: str) -> dict:
    """Category spend in a named window -- the live number for a tracker."""
    window = mq.resolve_window(mq.today_for_user(db, user_id), window_name)
    resolved = mq.resolve_category(db, category)
    return mq.spend_query(db, user_id, window, resolved)


def normalize_goal_kind(goal_type: str | None, name: str | None, category: str | None = None) -> tuple[str, str]:
    """Map a requested type (including legacy aliases) to save | track_spending and a name."""
    raw = (goal_type or "").strip()
    cleaned = (name or "").strip()
    if raw in LEGACY_SAVE_NAMES:
        return SAVE, cleaned or LEGACY_SAVE_NAMES[raw]
    if raw == SAVE:
        return SAVE, cleaned or DEFAULT_SAVE_NAME
    if raw == TRACK_SPENDING:
        return TRACK_SPENDING, cleaned
    raise GoalValidationError(f"type must be one of {sorted(GOAL_TYPES)}")


def create_goal(
    db: Session,
    user_id: UUID,
    goal_type: str,
    target_amount: float,
    target_date: date | None,
    category: str | None = None,
    window: str | None = None,
    name: str | None = None,
) -> Goal:
    if len(list_active_goals(db, user_id)) >= MAX_ACTIVE_GOALS:
        raise GoalLimitReached(f"You can have up to {MAX_ACTIVE_GOALS} active goals.")

    kind, title = normalize_goal_kind(goal_type, name, category)
    if kind == TRACK_SPENDING:
        goal = _new_spending_tracker(db, user_id, target_amount, category, window, title)
    else:
        goal = _new_savings_goal(db, user_id, target_amount, target_date, title)

    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def abandon_goal(db: Session, user_id: UUID, goal_id: UUID) -> Goal:
    """Drop an active goal so it no longer counts toward the five-slot cap.

    Sets status to abandoned rather than deleting the row, so history stays
    intact and the dashboard/chat tools (which only list actives) agree.
    """
    goal = (
        db.query(Goal)
        .filter(Goal.id == goal_id, Goal.user_id == user_id, Goal.status == "active")
        .one_or_none()
    )
    if goal is None:
        raise GoalNotFound()
    goal.status = "abandoned"
    db.commit()
    db.refresh(goal)
    return goal


def _new_savings_goal(
    db: Session, user_id: UUID, target_amount: float, target_date: date | None, name: str
) -> Goal:
    snapshot = _latest_snapshot(db, user_id)
    starting_amount = float(snapshot.total_assets) if snapshot else 0.0

    return Goal(
        user_id=user_id,
        type=SAVE,
        name=name,
        target_amount=target_amount,
        target_date=target_date,
        starting_amount=starting_amount,
        current_progress_amount=0,
        status="active",
    )


def _new_spending_tracker(
    db: Session,
    user_id: UUID,
    target_amount: float,
    category: str | None,
    window: str | None,
    name: str,
) -> Goal:
    if not category or not str(category).strip():
        raise GoalValidationError("category is required for a spending tracker")
    try:
        resolved = mq.resolve_category(db, category)
    except mq.QueryError as e:
        raise GoalValidationError(str(e), extra=e.extra) from e

    window_name = window or DEFAULT_TRACKING_WINDOW
    if window_name not in TRACKING_WINDOWS:
        raise GoalValidationError(f"window must be one of {list(TRACKING_WINDOWS)}")
    if target_amount < 0:
        raise GoalValidationError("target_amount must be zero or positive")

    spent = spend_for_tracker(db, user_id, resolved.name, window_name)["total_spent"]
    title = name.strip() if name and name.strip() else resolved.name
    return Goal(
        user_id=user_id,
        type=TRACK_SPENDING,
        name=title,
        target_amount=target_amount,
        target_date=None,
        starting_amount=0,
        current_progress_amount=spent,
        status="active",
        category=resolved.name,
        window=window_name,
    )


def recompute_goal_progress(db: Session, user_id: UUID, snapshot: NetWorthSnapshot) -> None:
    for goal in list_active_goals(db, user_id):
        if goal.type == TRACK_SPENDING:
            if not goal.category or not goal.window:
                continue
            try:
                goal.current_progress_amount = spend_for_tracker(
                    db, user_id, goal.category, goal.window
                )["total_spent"]
            except mq.QueryError:
                continue
            # Hitting a spending cap is over-budget, not "goal complete".
            continue

        goal.current_progress_amount = float(snapshot.total_assets) - float(goal.starting_amount)

        if goal.target_amount and float(goal.current_progress_amount) >= float(goal.target_amount):
            goal.status = "completed"
