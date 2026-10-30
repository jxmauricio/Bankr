from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import DevicePushToken, User

router = APIRouter(prefix="/devices", tags=["devices"])

_PLATFORMS = {"ios", "android"}


class PushTokenRequest(BaseModel):
    token: str = Field(min_length=8, max_length=256)
    platform: str = "ios"


@router.put("/push-token")
def register_push_token(
    body: PushTokenRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Remember this install so the weekly recap cron can find it."""
    platform = body.platform if body.platform in _PLATFORMS else "ios"
    token = body.token.strip()
    row = db.query(DevicePushToken).filter(DevicePushToken.token == token).one_or_none()
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(DevicePushToken(user_id=user.id, token=token, platform=platform, updated_at=now))
    else:
        row.user_id = user.id
        row.platform = platform
        row.updated_at = now
    db.commit()
    return {"ok": True}


@router.delete("/push-token", status_code=status.HTTP_204_NO_CONTENT)
def unregister_push_token(
    token: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    q = db.query(DevicePushToken).filter(DevicePushToken.user_id == user.id)
    if token:
        q = q.filter(DevicePushToken.token == token)
    q.delete(synchronize_session=False)
    db.commit()
