"""Sends the pushes that are due: the daily briefing from BRIEFING_READY_HOUR
and the weekly recap from Sunday's RECAP_READY_HOUR, in each user's time
zone. Run it every 15 minutes or so (`python -m app.jobs.notifications_job`
from cron); it's safe to run as often as you like, since each briefing and
recap is pushed once, keyed by its notification row (InsightLog).

Only users with a phone registered are visited: everyone else sees the same
briefing and recap in the app, made on first ask.
"""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import PushDevice, User
from app.integrations.push import PushSender, build_push_sender
from app.jobs import daily_briefing_job as briefing_job
from app.jobs import weekly_recap_job as recap_job
from app.services import money_query as mq
from app.services import push_service

logger = logging.getLogger(__name__)

BRIEFING_READY_HOUR = 8


def _local_hour(db: Session, user_id: UUID) -> int:
    user = db.get(User, user_id)
    return mq._now().astimezone(mq.user_zone(user.timezone if user else None)).hour


def push_daily_briefing(db: Session, sender: PushSender, user_id: UUID) -> bool:
    """Make today's briefing and push it, once, if it has anything in it."""
    if _local_hour(db, user_id) < BRIEFING_READY_HOUR or not push_service.get_prefs(db, user_id).daily_briefing:
        return False
    briefing = briefing_job.get_or_create_briefing(db, user_id)
    # The app may have logged it already (opened before now): it's been seen, no push.
    log = briefing_job.log_notification(db, briefing, delivered_via="push")
    if log is None:
        return False
    open_count = len(briefing.items)
    title = "Your daily briefing" if open_count > 1 else "One thing in your briefing"
    push_service.push_to_user(db, sender, user_id, "daily_briefing", title, log.message, {"day": briefing.day.isoformat()})
    return True


def push_weekly_recap(db: Session, sender: PushSender, user_id: UUID) -> bool:
    """Push the newest finished week's recap, once."""
    if not push_service.get_prefs(db, user_id).weekly_recap:
        return False
    week = recap_job.latest_week(db, user_id)
    if not recap_job.has_history_for(db, user_id, week):
        return False
    recap = recap_job.get_or_create_recap(db, user_id, week)
    if recap_job.notification_for(db, recap) is not None:
        return False
    recap_job.log_notification(db, recap, delivered_via="push")
    push_service.push_to_user(
        db,
        sender,
        user_id,
        "weekly_recap",
        recap_job.headline_for(recap.facts),
        recap_job.teaser_for(recap.facts),
        {"week_start": recap.week_start.isoformat()},
    )
    return True


def run_notifications_job(db: Session, sender: PushSender | None = None) -> dict:
    sender = sender or build_push_sender()
    counts = {"daily_briefing": 0, "weekly_recap": 0}
    user_ids = [u for (u,) in db.query(PushDevice.user_id).distinct()]
    for user_id in user_ids:
        for kind, push in (("daily_briefing", push_daily_briefing), ("weekly_recap", push_weekly_recap)):
            try:
                counts[kind] += push(db, sender, user_id)
            except Exception:
                db.rollback()
                logger.exception("%s push failed for user %s", kind, user_id)
    return counts


if __name__ == "__main__":
    from app.db.base import SessionLocal

    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as session:
        logger.info("notifications sent: %s", run_notifications_job(session))
