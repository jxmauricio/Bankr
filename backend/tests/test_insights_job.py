from datetime import date, timedelta

from app.db.models import Goal, InsightLog
from app.jobs import insights_job
from app.services.goal_service import create_goal
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient
from tests.fake_aggregator import FakeAggregatorClient


def test_no_insights_when_nothing_is_detected(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    create_goal(db, user.id, "save", target_amount=1000.0, target_date=date.today() + timedelta(days=365))

    logs = insights_job.run_insights_job(db, user.id)

    assert logs == []
    assert db.query(InsightLog).count() == 0


def test_goal_drift_gets_detected_and_phrased(db, user, monkeypatch):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    create_goal(db, user.id, "save", target_amount=1000.0, target_date=date.today() + timedelta(days=30))

    # Backdate the goal so get_goal_progress computes real elapsed pace
    # (a freshly created goal always looks "on pace" at day zero).
    goal = db.query(Goal).filter(Goal.user_id == user.id).one()
    goal.created_at = goal.created_at - timedelta(days=20)
    db.commit()

    monkeypatch.setattr(
        insights_job,
        "_client",
        FakeAgentClient(completions=["You're behind pace on your savings goal."]),
    )

    logs = insights_job.run_insights_job(db, user.id)

    assert len(logs) == 1
    assert logs[0].type == "goal_drift"
    assert logs[0].message == "You're behind pace on your savings goal."
    assert db.query(InsightLog).filter(InsightLog.user_id == user.id).count() == 1
