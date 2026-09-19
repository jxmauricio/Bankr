"""Proactive insights job: runs after each transaction sync.

Two-stage pattern, deliberately not "let the LLM watch everything":
1. Deterministic rule/threshold layer below decides *whether* something is
   worth telling the user about.
2. Only detected candidates get sent to Claude, and only to phrase them into
   a friendly, numbers-grounded message -- the LLM never decides on its own
   that a nudge should exist.

This keeps behavior testable (the rules are plain Python you can unit test)
and keeps LLM cost/latency bounded to actual events instead of every sync.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent import tools
from app.agent.agent_client import build_agent_client
from app.db.models import InsightLog

logger = logging.getLogger(__name__)

OVERSPEND_THRESHOLD = 1.3  # this month's category spend vs. trailing 3-month average

_client = build_agent_client()


@dataclass
class InsightCandidate:
    type: str  # overspend | goal_drift | unusual_transaction
    data: dict


def detect_candidates(db: Session, user_id: UUID) -> list[InsightCandidate]:
    candidates: list[InsightCandidate] = []

    goal_progress = tools.get_goal_progress(db, user_id)
    for goal in goal_progress.get("goals", []):
        if goal.get("on_pace") is False:
            candidates.append(InsightCandidate(type="goal_drift", data=goal))

    unusual = tools.get_unusual_transactions(db, user_id)
    for txn in unusual.get("unusual_transactions", []):
        candidates.append(InsightCandidate(type="unusual_transaction", data=txn))

    this_month = tools.get_spending(db, user_id, window="this_month", group_by="category")
    # NOTE: a real overspend check needs a trailing multi-month baseline per
    # category (compare_spending against previous months' same-point totals).
    # Wire in a baseline query here before enabling this in production --
    # left as a structural placeholder so the detection stage has a slot.
    _ = this_month

    return candidates


def _phrase_insight(candidate: InsightCandidate) -> str:
    return _client.complete(
        system=(
            "Turn this detected financial event into a single short, friendly, "
            "specific nudge message for the user (1-2 sentences). Use the exact "
            "numbers given. Do not give investment advice."
        ),
        user_message=f"Event type: {candidate.type}\nData: {candidate.data}",
    )


def run_insights_job(db: Session, user_id: UUID) -> list[InsightLog]:
    candidates = detect_candidates(db, user_id)
    logs = []
    for candidate in candidates:
        message = _phrase_insight(candidate)
        log = InsightLog(
            user_id=user_id,
            type=candidate.type,
            message=message,
            delivered_via="in_app",  # TODO: also dispatch via APNs once app/integrations/apns.py exists
        )
        db.add(log)
        logs.append(log)
    db.commit()
    return logs


def run_insights_job_safely(db: Session, user_id: UUID) -> None:
    """run_insights_job, swallowing any failure (e.g. no agent provider
    configured yet) so it never fails whatever triggered it -- a sync
    response the client is waiting on, or a webhook Plaid expects a prompt
    2xx from. Shared by app/api/accounts.py and app/services/webhook_service.py."""
    try:
        run_insights_job(db, user_id)
    except Exception:
        logger.exception("insights job failed for user %s", user_id)
