from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services.goal_service import (
    ACCEPTED_GOAL_TYPES,
    GOAL_TYPES,
    MAX_ACTIVE_GOALS,
    TRACK_SPENDING,
    GoalLimitReached,
    GoalNotFound,
    GoalValidationError,
    abandon_goal,
    create_goal,
)

router = APIRouter(prefix="/goals", tags=["goals"])


class CreateGoalRequest(BaseModel):
    type: str  # save | track_spending (legacy save_* aliases accepted)
    target_amount: float = 0
    target_date: date | None = None
    category: str | None = None
    window: str | None = None
    name: str | None = None


class GoalResponse(BaseModel):
    id: str
    type: str
    name: str | None = None
    target_amount: float
    target_date: date | None
    starting_amount: float
    current_progress_amount: float
    status: str
    category: str | None = None
    window: str | None = None


@router.post("", response_model=GoalResponse)
def set_goal(
    body: CreateGoalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoalResponse:
    if body.type not in ACCEPTED_GOAL_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"type must be one of {sorted(GOAL_TYPES)}")
    if body.type != TRACK_SPENDING and body.target_amount <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "target_amount must be positive")
    if body.type == TRACK_SPENDING and body.target_amount < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "target_amount must be zero or positive")

    try:
        goal = create_goal(
            db,
            user.id,
            body.type,
            body.target_amount,
            body.target_date,
            category=body.category,
            window=body.window,
            name=body.name,
        )
    except GoalLimitReached:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"You can have up to {MAX_ACTIVE_GOALS} active goals.",
        )
    except GoalValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return GoalResponse(
        id=str(goal.id),
        type=goal.type,
        name=goal.name,
        target_amount=float(goal.target_amount),
        target_date=goal.target_date,
        starting_amount=float(goal.starting_amount),
        current_progress_amount=float(goal.current_progress_amount),
        status=goal.status,
        category=goal.category,
        window=goal.window,
    )


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        abandon_goal(db, user.id, goal_id)
    except GoalNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Goal not found")
