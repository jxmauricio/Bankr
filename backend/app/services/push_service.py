"""Which pushes each user wants, and sending one to their phones.

Phones register at /devices/push-token (app/api/devices.py); pushes go out
through APNs (app/integrations/apns.py), which is a no-op until it's
configured.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import DevicePushToken, NotificationPrefs
from app.integrations import apns

KINDS = ("daily_briefing", "weekly_recap")


def get_prefs(db: Session, user_id: UUID) -> NotificationPrefs:
    """The user's push choices; the defaults (everything on) when they've never changed one."""
    return db.get(NotificationPrefs, user_id) or NotificationPrefs(user_id=user_id, daily_briefing=True, weekly_recap=True)


def wants(db: Session, user_id: UUID, kind: str) -> bool:
    return kind in KINDS and getattr(get_prefs(db, user_id), kind)


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
    devices = db.query(DevicePushToken).filter(DevicePushToken.user_id == user_id).count()
    return {"daily_briefing": prefs.daily_briefing, "weekly_recap": prefs.weekly_recap, "device_count": devices}


def push_to_user(db: Session, user_id: UUID, kind: str, title: str, body: str, data: dict | None = None) -> int:
    """Send to every phone the user has, if they want this kind. Returns how
    many it reached; tokens APNs no longer knows are forgotten."""
    if not wants(db, user_id, kind):
        return 0
    sent = 0
    for row in db.query(DevicePushToken).filter(DevicePushToken.user_id == user_id).all():
        result = apns.send_alert(row.token, title, body, {"type": kind, **(data or {})})
        if result == apns.GONE:
            db.delete(row)
        elif result == apns.SENT:
            sent += 1
    db.commit()
    return sent
