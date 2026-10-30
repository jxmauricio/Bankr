from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services import push_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


class DeviceRequest(BaseModel):
    token: str = Field(max_length=push_service.MAX_TOKEN_LENGTH)
    platform: Literal["ios", "android"] | None = None


class SettingsRequest(BaseModel):
    daily_briefing: bool | None = None
    weekly_recap: bool | None = None


@router.post("/devices", status_code=status.HTTP_204_NO_CONTENT)
def register_device(body: DeviceRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """The mobile app sends its Expo push token after the user allows notifications."""
    try:
        push_service.register_device(db, user.id, body.token, body.platform)
    except push_service.PushTokenError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/devices/remove", status_code=status.HTTP_204_NO_CONTENT)
def unregister_device(body: DeviceRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """Signing out on the phone."""
    push_service.unregister_device(db, user.id, body.token)


@router.get("/settings")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return push_service.prefs_dict(db, user.id)


@router.patch("/settings")
def update_settings(body: SettingsRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    push_service.update_prefs(db, user.id, **body.model_dump())
    return push_service.prefs_dict(db, user.id)
