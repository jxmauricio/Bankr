from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services import budget_service as bs
from app.services import money_query as mq

router = APIRouter(prefix="/budgets", tags=["budgets"])


class SettingsRequest(BaseModel):
    mode: Literal["flex", "category"] | None = None
    flex_amount: float | None = Field(default=None, ge=0)
    flex_rollover: bool | None = None


class BudgetRequest(BaseModel):
    amount: float | None = Field(default=None, ge=0)
    group: Literal["fixed", "flex"] | None = None
    rollover: bool | None = None


class MoveRequest(BaseModel):
    month: str | None = None  # YYYY-MM, default this month
    from_key: str  # category id, or "flex"
    to_key: str
    amount: float = Field(gt=0)


class SetupLine(BaseModel):
    category_id: UUID
    amount: float = Field(ge=0)
    group: Literal["fixed", "flex"] = "flex"
    rollover: bool | None = None


class SetupRequest(BaseModel):
    mode: Literal["flex", "category"] = "flex"
    flex_amount: float = Field(default=0, ge=0)
    lines: list[SetupLine]


def _bad(e: bs.BudgetError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


def _month(db: Session, user: User, value: str | None):
    try:
        return bs.parse_month(value, mq.today_for_user(db, user.id))
    except bs.BudgetError as e:
        raise _bad(e)


@router.get("")
def get_budget(month: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    result = bs.budget_status(db, user.id, _month(db, user, month))
    db.commit()  # get_settings may have created the default settings row
    return result


@router.get("/suggestion")
def suggestion(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    result = bs.suggest_budget(db, user.id)
    db.commit()
    return result


@router.post("/setup")
def setup(body: SetupRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        bs.setup_budget(
            db, user.id, mode=body.mode, flex_amount=body.flex_amount, lines=[line.model_dump() for line in body.lines]
        )
    except bs.BudgetError as e:
        db.rollback()
        raise _bad(e)
    db.commit()
    return bs.budget_status(db, user.id)


@router.put("/settings")
def put_settings(body: SettingsRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        bs.update_settings(db, user.id, **body.model_dump(exclude_none=True))
    except bs.BudgetError as e:
        raise _bad(e)
    db.commit()
    return bs.budget_status(db, user.id)


@router.post("/moves", status_code=status.HTTP_201_CREATED)
def move(body: MoveRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    month = _month(db, user, body.month)
    try:
        bs.move_money(db, user.id, month, body.from_key, body.to_key, body.amount)
    except bs.BudgetError as e:
        raise _bad(e)
    db.commit()
    return bs.budget_status(db, user.id, month)


@router.put("/{category_id}")
def put_budget(
    category_id: UUID, body: BudgetRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    try:
        bs.upsert_budget(db, user.id, category_id, **body.model_dump(exclude_none=True))
    except bs.BudgetError as e:
        raise _bad(e)
    db.commit()
    return bs.budget_status(db, user.id)


@router.delete("/{category_id}")
def remove_budget(category_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not bs.delete_budget(db, user.id, category_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no budget for that category")
    db.commit()
    return bs.budget_status(db, user.id)
