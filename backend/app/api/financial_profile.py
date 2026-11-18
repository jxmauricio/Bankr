from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services.financial_profile import (
    KNOWLEDGE,
    LIFESTYLES,
    OCCUPATIONS,
    ProfileError,
    save_profile,
)

router = APIRouter(prefix="/financial-profile", tags=["financial-profile"])


class DebtIn(BaseModel):
    name: str
    owed: float = 0
    paid_off: float = 0


class InvestmentIn(BaseModel):
    name: str
    amount: float = 0


class GoalIn(BaseModel):
    name: str
    target: float | None = None
    saved: float | None = None


class AnswersIn(BaseModel):
    age: int
    occupation: str
    monthly_income: float
    cash: float = 0
    emergency_fund: float = 0
    housing: str = "none"
    housing_payment: float = 0
    debts: list[DebtIn] = []
    investments: list[InvestmentIn] = []
    goals: list[GoalIn] = []
    knowledge: str
    lifestyle: str


class SaveProfileRequest(BaseModel):
    path: str
    story: str | None = Field(default=None, max_length=8000)
    answers: AnswersIn | None = None


@router.get("")
def get_profile(user: User = Depends(get_current_user)) -> dict:
    return {
        "completed": user.onboarding_completed_at is not None,
        "markdown": user.financial_profile_md,
        "occupations": OCCUPATIONS,
        "knowledge": {k: {"label": v[0], "blurb": v[1]} for k, v in KNOWLEDGE.items()},
        "lifestyles": {k: {"label": v[0], "blurb": v[1]} for k, v in LIFESTYLES.items()},
    }


@router.put("")
def put_profile(
    body: SaveProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        answers = body.answers.model_dump() if body.answers else None
        save_profile(db, user, body.path, body.story, answers)
    except ProfileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.commit()
    db.refresh(user)
    return {"completed": True, "markdown": user.financial_profile_md}
