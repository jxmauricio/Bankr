from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services.goal_service import GOAL_TYPES, create_goal

router = APIRouter(prefix="/goals", tags=["goals"])


class CreateGoalRequest(BaseModel):
    type: str  # save_amount | pay_off_debt | build_emergency_fund
    target_amount: float
    target_date: date | None = None


class GoalResponse(BaseModel):
    id: str
    type: str
    target_amount: float
    target_date: date | None
    starting_amount: float
    current_progress_amount: float
    status: str


@router.post("", response_model=GoalResponse)
def set_goal(
    body: CreateGoalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoalResponse:
    if body.type not in GOAL_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"type must be one of {sorted(GOAL_TYPES)}")
    if body.target_amount <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "target_amount must be positive")

    goal = create_goal(db, user.id, body.type, body.target_amount, body.target_date)
    return GoalResponse(
        id=str(goal.id),
        type=goal.type,
        target_amount=float(goal.target_amount),
        target_date=goal.target_date,
        starting_amount=float(goal.starting_amount),
        current_progress_amount=float(goal.current_progress_amount),
        status=goal.status,
    )
