"""Pushes the daily briefing from BRIEFING_READY_HOUR in each user's time
zone, once per day, keyed by its notification row (InsightLog). It runs
every 15 minutes on the API's scheduler (weekly_recap_job.start_scheduler)
and is safe to run as often as you like.

Only users with a phone registered are visited: everyone else sees the same
briefing in the app, made on first ask. If the app showed it first, there's
no push.

    python -m app.jobs.briefing_push_job
"""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import DevicePushToken, User
from app.jobs import daily_briefing_job as briefing_job
from app.services import money_query as mq
from app.services import push_service

logger = logging.getLogger(__name__)

BRIEFING_READY_HOUR = 8


def _local_hour(db: Session, user_id: UUID) -> int:
    user = db.get(User, user_id)
    return mq._now().astimezone(mq.user_zone(user.timezone if user else None)).hour


def push_daily_briefing(db: Session, user_id: UUID) -> bool:
    """Make today's briefing and push it, once, if it has anything in it."""
    if _local_hour(db, user_id) < BRIEFING_READY_HOUR or not push_service.wants(db, user_id, "daily_briefing"):
        return False
    briefing = briefing_job.get_or_create_briefing(db, user_id)
    # None when the app logged it already (opened before now): it's been seen, no push.
    log = briefing_job.log_notification(db, briefing)
    if log is None:
        return False
    title = "Your daily briefing" if len(briefing.items) > 1 else "One thing in your briefing"
    if push_service.push_to_user(db, user_id, "daily_briefing", title, log.message, {"day": briefing.day.isoformat()}):
        log.delivered_via = "push"
        db.commit()
    return True


def run_due_briefings(db: Session) -> int:
    pushed = 0
    for (user_id,) in db.query(DevicePushToken.user_id).distinct().all():
        try:
            pushed += push_daily_briefing(db, user_id)
        except Exception:
            db.rollback()
            logger.exception("daily briefing push failed for user %s", user_id)
    return pushed


def cron_tick() -> None:
    from app.db.base import get_session_factory

    db = get_session_factory()()
    try:
        pushed = run_due_briefings(db)
        if pushed:
            logger.info("daily briefing cron delivered %s briefing(s)", pushed)
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cron_tick()
