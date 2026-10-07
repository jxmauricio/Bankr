from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from app.services import money_query as mq
from app.services.money_query import QueryError

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Calendar periods to date: "month" is since the 1st, not the last 30 days.
Period = Literal["week", "month", "year"]


def _query_error(e: QueryError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": str(e), **e.extra})


@router.get("/net-worth")
def net_worth(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return get_net_worth_history(db, user.id)


@router.get("/spending")
def spending(
    period: Period = "month",
    window: str | None = None,
    start: str | None = None,
    end: str | None = None,
    category: str | None = None,
    merchant: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """window/start/end override period; start/end/category/merchant are
    exactly what a chat source chip carries (see claude_agent._source_query)
    so tapping one lists the rows behind that answer."""
    try:
        return get_itemized_transactions(
            db, user.id, "expense", period, window, start, end, category=category, merchant=merchant
        )
    except QueryError as e:
        raise _query_error(e) from e


@router.get("/income")
def income(
    period: Period = "month",
    window: str | None = None,
    start: str | None = None,
    end: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return get_itemized_transactions(db, user.id, "income", period, window, start, end)
    except QueryError as e:
        raise _query_error(e) from e


@router.get("/rollup")
def rollup(
    period: Period = "month",
    window: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return get_period_rollup(db, user.id, period, window)
    except QueryError as e:
        raise _query_error(e) from e


@router.get("/transactions")
def transactions(
    window: str = "this_month",
    start: str | None = None,
    end: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Every transaction in the window, with its account (the Transactions view)."""
    try:
        w = mq.resolve_window(mq.today_for_user(db, user.id), window, start, end)
    except QueryError as e:
        raise _query_error(e) from e
    return {**mq.list_transactions(db, user.id, w), "as_of": mq.data_freshness(db, user.id)}


@router.get("/cash-flow")
def cash_flow(
    window: str = "this_month",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Income by payer and spending by category for the Cash flow view."""
    try:
        w = mq.resolve_window(mq.today_for_user(db, user.id), window)
    except QueryError as e:
        raise _query_error(e) from e
    return {**mq.cash_flow_breakdown(db, user.id, w), "as_of": mq.data_freshness(db, user.id)}


@router.get("/spending-pace")
def spending_pace(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Running spending by day of month, this month against last."""
    return mq.spending_pace(db, user.id)


@router.get("/average")
def average(
    basis: Literal["month", "year"] = "month",
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Average income and spending per month (or per year) over the last
    12 complete months. With `month` (YYYY-MM), that one month's totals
    instead."""
    try:
        result = mq.month_cash_flow(db, user.id, month) if month else mq.average_cash_flow(db, user.id, basis)
    except QueryError as e:
        raise _query_error(e) from e
    return {**result, "as_of": mq.data_freshness(db, user.id)}


@router.get("/months")
def months(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[str]:
    """Months (YYYY-MM, newest first) that can be picked for a month view."""
    return mq.available_months(db, user.id)


@router.get("/goal-progress")
def goal_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return get_goal_progress(db, user.id)
