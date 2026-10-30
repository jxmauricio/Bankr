from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.integrations.web_search import build_web_search_client
from app.jobs import daily_briefing_job as job
from app.services import briefing_actions as actions
from app.services.sync_service import refresh_net_worth

router = APIRouter(prefix="/briefing", tags=["briefing"])

_search_client = build_web_search_client()


class ActionRequest(BaseModel):
    item_key: str = Field(max_length=200)
    action: Literal["recategorize", "create_rule", "mark_expected", "dismiss"]
    category_id: UUID | None = None
    # False (the default) only says what would change; True does it.
    confirm: bool = False


@router.get("/today")
def today(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Today's briefing, made on first ask, which also puts it in the notifications list."""
    return {"briefing": job.briefing_dict(db, job.get_or_create_briefing(db, user.id, notify=True))}


@router.post("/actions")
def run_action(body: ActionRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        result = actions.run_action(db, user.id, body.item_key, body.action, body.category_id, body.confirm)
    except actions.ItemNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "briefing item not found")
    except actions.BriefingActionError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    if not body.confirm:
        db.rollback()
        return result
    if body.action in ("recategorize", "create_rule"):
        refresh_net_worth(db, user.id)  # commits, and keeps spending-goal progress current
    else:
        db.commit()
    briefing = job.get_or_create_briefing(db, user.id)
    return {**result, "briefing": job.briefing_dict(db, briefing)}


@router.get("/help")
def item_help(
    item_key: str = Query(max_length=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Where to cancel, and emails to copy. Bankr never sends them."""
    try:
        return actions.item_help(db, user.id, item_key, _search_client)
    except actions.ItemNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "briefing item not found")
    except actions.BriefingActionError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """Opening today's briefing marks its notification read."""
    briefing = job.get_or_create_briefing(db, user.id)
    notification = job.notification_for(db, briefing)
    if notification is not None and notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
