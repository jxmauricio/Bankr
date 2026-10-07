"""Everything that should run after fresh transactions arrive, in order:
recurring detection first (the insights job reads its price changes), then
insights. Each step swallows its own failures so a sync never fails on them."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.jobs.insights_job import run_insights_job_safely
from app.services.recurring_service import detect_recurring_safely


def run_post_sync_jobs(db: Session, user_id: UUID) -> None:
    detect_recurring_safely(db, user_id)
    run_insights_job_safely(db, user_id)
