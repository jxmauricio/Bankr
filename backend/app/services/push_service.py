"""Phones to push to, which pushes each user wants, and sending one."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import NotificationPrefs, PushDevice
from app.integrations.push import PushMessage, PushSender

KINDS = ("daily_briefing", "weekly_recap")
MAX_TOKEN_LENGTH = 200


class PushTokenError(ValueError):
    pass


def register_device(db: Session, user_id: UUID, token: str, platform: str | None) -> PushDevice:
    """Remember a phone's Expo push token for this user. The same token
    signed in to another account moves here: a phone pushes to whoever is
    signed in on it."""
    token = (token or "").strip()
    if not (token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")) or len(token) > MAX_TOKEN_LENGTH:
        raise PushTokenError("not an Expo push token")
    device = db.query(PushDevice).filter(PushDevice.token == token).one_or_none()
    if device is None:
        device = PushDevice(user_id=user_id, token=token)
        db.add(device)
    device.user_id = user_id
    device.platform = platform
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return device


def unregister_device(db: Session, user_id: UUID, token: str) -> None:
    """Signing out on a phone: stop pushing this account's news to it."""
    db.query(PushDevice).filter(PushDevice.user_id == user_id, PushDevice.token == token).delete()
    db.commit()


def get_prefs(db: Session, user_id: UUID) -> NotificationPrefs:
    """The user's push choices; the defaults (everything on) when they've never changed one."""
    return db.get(NotificationPrefs, user_id) or NotificationPrefs(user_id=user_id, daily_briefing=True, weekly_recap=True)


def update_prefs(db: Session, user_id: UUID, **changes: bool) -> NotificationPrefs:
    prefs = db.get(NotificationPrefs, user_id)
    if prefs is None:
        prefs = NotificationPrefs(user_id=user_id, daily_briefing=True, weekly_recap=True)
        db.add(prefs)
    for kind, on in changes.items():
        if kind in KINDS and on is not None:
            setattr(prefs, kind, on)
    db.commit()
    return prefs


def prefs_dict(db: Session, user_id: UUID) -> dict:
    prefs = get_prefs(db, user_id)
    devices = db.query(PushDevice).filter(PushDevice.user_id == user_id).count()
    return {"daily_briefing": prefs.daily_briefing, "weekly_recap": prefs.weekly_recap, "device_count": devices}


def push_to_user(db: Session, sender: PushSender, user_id: UUID, kind: str, title: str, body: str, data: dict | None = None) -> int:
    """Send to every phone the user has, if they want this kind. Returns how
    many it reached; tokens for uninstalled apps are forgotten."""
    if kind not in KINDS or not getattr(get_prefs(db, user_id), kind):
        return 0
    tokens = [t for (t,) in db.query(PushDevice.token).filter(PushDevice.user_id == user_id)]
    if not tokens:
        return 0
    result = sender.send([PushMessage(token=t, title=title, body=body, data={"kind": kind, **(data or {})}) for t in tokens])
    if result.dead_tokens:
        db.query(PushDevice).filter(PushDevice.token.in_(result.dead_tokens)).delete(synchronize_session=False)
        db.commit()
    return result.sent
