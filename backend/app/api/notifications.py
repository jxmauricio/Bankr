from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services import push_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


class SettingsRequest(BaseModel):
    daily_briefing: bool | None = None
    weekly_recap: bool | None = None


@router.get("/settings")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return push_service.prefs_dict(db, user.id)


@router.patch("/settings")
def update_settings(body: SettingsRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    push_service.update_prefs(db, user.id, **body.model_dump())
    return push_service.prefs_dict(db, user.id)
