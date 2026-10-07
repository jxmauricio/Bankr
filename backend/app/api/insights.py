from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import InsightLog, User

router = APIRouter(prefix="/insights", tags=["insights"])

MAX_LISTED = 50


def _insight(log: InsightLog) -> dict:
    # The dedupe key names what the insight is about, e.g.
    # "budget_overspend:<line>:<month>:over"; the client uses it to link there.
    subject = (log.dedupe_key or "").split(":")
    return {
        "id": str(log.id),
        "type": log.type,
        "message": log.message,
        "transaction_ids": log.related_transaction_ids or [],
        "subject_id": subject[1] if len(subject) > 1 else None,
        "created_at": log.created_at.isoformat(),
        "read": log.read_at is not None,
    }


@router.get("")
def list_insights(
    unread_only: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    q = db.query(InsightLog).filter(InsightLog.user_id == user.id)
    unread = q.filter(InsightLog.read_at.is_(None)).count()
    if unread_only:
        q = q.filter(InsightLog.read_at.is_(None))
    rows = q.order_by(InsightLog.created_at.desc()).limit(MAX_LISTED).all()
    return {"unread_count": unread, "insights": [_insight(r) for r in rows]}


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    db.query(InsightLog).filter(InsightLog.user_id == user.id, InsightLog.read_at.is_(None)).update(
        {InsightLog.read_at: datetime.now(timezone.utc)}, synchronize_session=False
    )
    db.commit()


@router.post("/{insight_id}/read")
def mark_read(insight_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    log = db.query(InsightLog).filter(InsightLog.id == insight_id, InsightLog.user_id == user.id).one_or_none()
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "insight not found")
    if log.read_at is None:
        log.read_at = datetime.now(timezone.utc)
        db.commit()
    return _insight(log)
