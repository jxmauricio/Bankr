from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User, WeeklyRecap
from app.jobs import weekly_recap_job as job
from app.services import money_query as mq

router = APIRouter(prefix="/recaps", tags=["recaps"])


def _recap(db: Session, recap: WeeklyRecap, latest: mq.Window) -> dict:
    notification = job.notification_for(db, recap)
    previous = job.week_starting(recap.week_start - timedelta(days=7))
    return {
        "week_start": recap.week_start.isoformat(),
        "week_end": recap.week_end.isoformat(),
        "label": mq.format_range(recap.week_start, recap.week_end),
        # From the saved numbers, so a wording change reaches recaps already made.
        "headline": job.headline_for(recap.facts),
        "teaser": job.teaser_for(recap.facts),
        "summary": recap.summary,
        "facts": recap.facts,
        "created_at": recap.created_at.isoformat(),
        # Only the latest week is a notification; a past week counts as read.
        "read": notification is None or notification.read_at is not None,
        "previous_week_start": previous.start.isoformat() if job.has_history_for(db, recap.user_id, previous) else None,
        "next_week_start": (
            (recap.week_start + timedelta(days=7)).isoformat() if recap.week_start < latest.start else None
        ),
    }


@router.get("/latest")
def latest_recap(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """The newest finished week's recap, made on first ask. Null until
    there's a week of history to recap."""
    week = job.latest_week(db, user.id)
    if not job.has_history_for(db, user.id, week):
        return {"recap": None}
    return {"recap": _recap(db, job.get_or_create_recap(db, user.id, week, notify=True), week)}


@router.get("/{week_start}")
def recap_for_week(week_start: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    latest = job.latest_week(db, user.id)
    if week_start.weekday() != 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "week_start must be a Monday")
    if week_start > latest.start:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "that week isn't over yet")
    week = job.week_starting(week_start)
    if not job.has_history_for(db, user.id, week):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no transactions that far back")
    return {"recap": _recap(db, job.get_or_create_recap(db, user.id, week, notify=week_start == latest.start), latest)}


@router.post("/{week_start}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_recap_read(week_start: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """Opening the recap, or dismissing its card on the home screen."""
    recap = (
        db.query(WeeklyRecap)
        .filter(WeeklyRecap.user_id == user.id, WeeklyRecap.week_start == week_start)
        .one_or_none()
    )
    if recap is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recap not found")
    notification = job.notification_for(db, recap)
    if notification is not None and notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
