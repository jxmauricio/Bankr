from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.tools import get_goal_progress
from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services.dashboard_service import (
    get_holdings,
    get_itemized_transactions,
    get_net_worth_history,
    get_period_rollup,
)
from app.services import money_query as mq
from app.services.recurring_service import series_charges
from app.services.money_query import QueryError
from app.services.cash_flow_plan import delete_income, money_left_plan, upsert_income
from app.services.spending_health import spending_health

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Calendar periods to date: "month" is since the 1st, not the last 30 days.
Period = Literal["week", "month", "year"]


def _query_error(e: QueryError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": str(e), **e.extra})


@router.get("/net-worth")
def net_worth(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return get_net_worth_history(db, user.id)


@router.get("/holdings")
def holdings(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Positions in linked brokerages. Price is Plaid's last close, refreshed
    on bank sync -- not a live quote."""
    return get_holdings(db, user.id)


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
    merchant: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return get_itemized_transactions(db, user.id, "income", period, window, start, end, merchant=merchant)
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
    account_id: UUID | None = None,
    recurring_id: UUID | None = None,
    merchant: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Every transaction in the window, with its account (the Transactions view).
    account_id narrows it to one account and recurring_id to one recurring
    series' payments -- what a chat chart's net-worth or subscription row opens.
    merchant is what a transfer/all source chip carries."""
    try:
        w = mq.resolve_window(mq.today_for_user(db, user.id), window, start, end)
        if recurring_id is not None:
            listing = series_charges(db, user.id, recurring_id, w)
        else:
            listing = mq.list_transactions(db, user.id, w, account_id, merchant=merchant)
    except QueryError as e:
        raise _query_error(e) from e
    return {**listing, "as_of": mq.data_freshness(db, user.id)}


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


class UpsertIncomeRequest(BaseModel):
    id: UUID | None = None
    series_id: UUID | None = None
    payer: str | None = None
    name: str
    amount: float
    cadence: str = "monthly"
    included: bool = True


@router.get("/money-left")
def money_left(
    window: str = "this_month",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Expected income for the window, including paychecks still ahead.
    `left` is that pay minus tracker budgets minus spending that isn't in
    any of those budgets — what Budget shows as money left."""
    try:
        return money_left_plan(db, user.id, window)
    except QueryError as e:
        raise _query_error(e) from e


@router.put("/money-left/incomes")
def put_income(
    body: UpsertIncomeRequest,
    window: str = "this_month",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        upsert_income(
            db,
            user.id,
            income_id=body.id,
            series_id=body.series_id,
            payer=body.payer,
            name=body.name,
            amount=body.amount,
            cadence=body.cadence,
            included=body.included,
        )
    except QueryError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return money_left_plan(db, user.id, window)


@router.delete("/money-left/incomes/{income_id}")
def remove_income(
    income_id: UUID,
    window: str = "this_month",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        delete_income(db, user.id, income_id)
    except QueryError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return money_left_plan(db, user.id, window)


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


@router.get("/health")
def health(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Average monthly spending by category as a share of income, scored
    against widely cited guidelines (HUD housing, 50/30/20, common budget
    shares). Uses the same complete months as /dashboard/average."""
    return spending_health(db, user.id)
