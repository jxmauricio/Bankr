from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.tools import get_goal_progress
from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services.dashboard_service import (
    get_itemized_transactions,
    get_net_worth_history,
    get_period_rollup,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

Period = Literal["week", "month", "year"]


@router.get("/net-worth")
def net_worth(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return get_net_worth_history(db, user.id)


@router.get("/spending")
def spending(
    period: Period = "month", user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return get_itemized_transactions(db, user.id, kind="expense", period=period)


@router.get("/income")
def income(
    period: Period = "month", user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return get_itemized_transactions(db, user.id, kind="income", period=period)


@router.get("/rollup")
def rollup(
    period: Period = "month", user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return get_period_rollup(db, user.id, period)


@router.get("/goal-progress")
def goal_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return get_goal_progress(db, user.id)
