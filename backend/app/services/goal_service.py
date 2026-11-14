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
MAX_ACTIVE_GOALS = 5  # savings goals only; spending trackers are uncapped

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


def list_active_save_goals(db: Session, user_id: UUID) -> list[Goal]:
    """Savings goals that count toward the five-slot cap. Trackers do not."""
    return (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active", Goal.type == SAVE)
        .order_by(Goal.created_at.asc())
        .all()
    )


def spend_for_tracker(db: Session, user_id: UUID, category: mq.ResolvedCategory, window_name: str) -> dict:
    """Category spend in a named window -- the live number for a tracker."""
    window = mq.resolve_window(mq.today_for_user(db, user_id), window_name)
    return mq.spend_query(db, user_id, window, category)


def tracker_category(db: Session, user_id: UUID, goal: Goal) -> mq.ResolvedCategory | None:
    """What a spending tracker watches, or None for a savings goal. Raises
    QueryError if its stored category is gone.

    Trackers created before category ids (or left behind when a rename
    dropped the old name column) may only have `goal.name`. Resolve that
    the same way Centsio does, including aliases like "dining" → Eating Out,
    so Budget and chat don't keep a frozen spend figure.
    """
    if goal.category_slice:
        return mq.resolve_category(db, goal.category_slice, user_id)
    if goal.group_id or goal.category_id:
        return mq.resolve_stored(db, user_id, group_id=goal.group_id, category_id=goal.category_id)
    if goal.merchant or not (goal.name or "").strip():
        return None
    try:
        return mq.resolve_category(db, goal.name, user_id)
    except mq.QueryError:
        return None


def _reattach_tracker(goal: Goal, category: mq.ResolvedCategory) -> None:
    """Fill in ids on a name-only tracker so the next sync doesn't rely on the name."""
    if goal.category_slice or goal.group_id or goal.category_id:
        return
    goal.group_id = category.group_id
    goal.category_id = category.category_id
    goal.category_slice = category.slice


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
    merchant: str | None = None,
) -> Goal:
    kind, title = normalize_goal_kind(goal_type, name, category)
    if kind == SAVE and len(list_active_save_goals(db, user_id)) >= MAX_ACTIVE_GOALS:
        raise GoalLimitReached(f"You can have up to {MAX_ACTIVE_GOALS} active goals.")
    if kind == TRACK_SPENDING:
        goal = _apply_spending_tracker(db, user_id, target_amount, category, window, title, merchant=merchant)
        db.add(goal)
    else:
        goal = _new_savings_goal(db, user_id, target_amount, target_date, title)
        db.add(goal)

    db.commit()
    db.refresh(goal)
    return goal


def update_goal(
    db: Session,
    user_id: UUID,
    goal_id: UUID,
    *,
    target_amount: float,
    category: str | None = None,
    merchant: str | None = None,
    window: str | None = None,
    name: str | None = None,
) -> Goal:
    """Change an active spending tracker's name, limit, window, or what it watches."""
    goal = (
        db.query(Goal)
        .filter(Goal.id == goal_id, Goal.user_id == user_id, Goal.status == "active")
        .one_or_none()
    )
    if goal is None:
        raise GoalNotFound()
    if goal.type != TRACK_SPENDING:
        raise GoalValidationError("only a spending tracker can be edited this way")
    title = (name or "").strip()
    _apply_spending_tracker(
        db, user_id, target_amount, category, window, title, merchant=merchant, goal=goal
    )
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


def _apply_spending_tracker(
    db: Session,
    user_id: UUID,
    target_amount: float,
    category: str | None,
    window: str | None,
    name: str,
    merchant: str | None = None,
    goal: Goal | None = None,
) -> Goal:
    merch = (merchant or "").strip() or None
    cat = (category or "").strip() or None
    if merch and cat:
        raise GoalValidationError("use a category or a vendor, not both")
    if not merch and not cat:
        raise GoalValidationError("category or merchant is required for a spending tracker")
    if merch and len(merch) < 2:
        raise GoalValidationError("merchant needs at least 2 characters")

    window_name = window or DEFAULT_TRACKING_WINDOW
    if window_name not in TRACKING_WINDOWS:
        raise GoalValidationError(f"window must be one of {list(TRACKING_WINDOWS)}")
    if target_amount < 0:
        raise GoalValidationError("target_amount must be zero or positive")

    if goal is None:
        goal = Goal(
            user_id=user_id,
            type=TRACK_SPENDING,
            target_date=None,
            starting_amount=0,
            status="active",
        )

    if merch:
        today = mq.today_for_user(db, user_id)
        spent = mq.spend_query(db, user_id, mq.resolve_window(today, window_name), merchant=merch)["total_spent"]
        goal.name = name.strip() if name and name.strip() else merch
        goal.target_amount = target_amount
        goal.current_progress_amount = spent
        goal.merchant = merch
        goal.window = window_name
        goal.group_id = None
        goal.category_id = None
        goal.category_slice = None
        return goal

    try:
        resolved = mq.resolve_category(db, cat, user_id)
    except mq.QueryError as e:
        raise GoalValidationError(str(e), extra=e.extra) from e

    spent = spend_for_tracker(db, user_id, resolved, window_name)["total_spent"]
    goal.name = name.strip() if name and name.strip() else resolved.name
    goal.target_amount = target_amount
    goal.current_progress_amount = spent
    goal.merchant = None
    goal.window = window_name
    goal.group_id = resolved.group_id
    goal.category_id = resolved.category_id
    goal.category_slice = resolved.slice
    return goal


def recompute_goal_progress(db: Session, user_id: UUID, snapshot: NetWorthSnapshot) -> None:
    for goal in list_active_goals(db, user_id):
        if goal.type == TRACK_SPENDING:
            try:
                if not goal.window:
                    continue
                if goal.merchant:
                    today = mq.today_for_user(db, user_id)
                    goal.current_progress_amount = mq.spend_query(
                        db, user_id, mq.resolve_window(today, goal.window), merchant=goal.merchant
                    )["total_spent"]
                    continue
                category = tracker_category(db, user_id, goal)
                if category is None:
                    continue
                _reattach_tracker(goal, category)
                goal.current_progress_amount = spend_for_tracker(db, user_id, category, goal.window)["total_spent"]
            except mq.QueryError:
                continue
            # Hitting a spending cap is over-budget, not "goal complete".
            continue

        goal.current_progress_amount = float(snapshot.total_assets) - float(goal.starting_amount)

        if goal.target_amount and float(goal.current_progress_amount) >= float(goal.target_amount):
            goal.status = "completed"
