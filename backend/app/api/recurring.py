from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import RecurringSeries, User
from app.services import money_query as mq
from app.services.recurring_service import recurring_overview, series_dict

router = APIRouter(prefix="/recurring", tags=["recurring"])


class UpdateSeriesRequest(BaseModel):
    status: Literal["suggested", "confirmed", "dismissed"] | None = None
    kind: Literal["bill", "subscription", "income"] | None = None
    name: str | None = None


@router.get("")
def list_recurring(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return recurring_overview(db, user.id)


@router.patch("/{series_id}")
def update_series(
    series_id: UUID,
    body: UpdateSeriesRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    series = (
        db.query(RecurringSeries)
        .filter(RecurringSeries.id == series_id, RecurringSeries.user_id == user.id)
        .one_or_none()
    )
    if series is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recurring series not found")
    if body.status is not None:
        series.status = body.status
    if body.kind is not None:
        series.kind = body.kind
    if body.name is not None and body.name.strip():
        series.display_name = body.name.strip()[:120]
    db.commit()
    return series_dict(series, mq.today_for_user(db, user.id))
