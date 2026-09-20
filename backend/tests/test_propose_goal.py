from datetime import date

from app.agent.tools import propose_goal
from app.db.models import Goal
from app.services.goal_service import create_goal


def test_propose_goal_drafts_without_writing(db, user):
    result = propose_goal(db, user.id, type="save_amount", target_amount=5000, target_date="2027-06-01")

    assert result["status"] == "proposed"
    assert result["proposal"] == {
        "type": "save_amount",
        "target_amount": 5000.0,
        "target_date": "2027-06-01",
        "replaces_existing": False,
        "at_limit": False,
        "active_count": 0,
        "slots_remaining": 5,
    }
    assert db.query(Goal).filter(Goal.user_id == user.id).count() == 0


def test_propose_goal_adds_alongside_an_active_goal(db, user):
    create_goal(db, user.id, "pay_off_debt", 2000.0, date(2027, 1, 1))

    result = propose_goal(db, user.id, type="build_emergency_fund", target_amount=8000)

    assert result["proposal"]["replaces_existing"] is False
    assert result["proposal"]["at_limit"] is False
    assert result["proposal"]["active_count"] == 1
    assert result["proposal"]["slots_remaining"] == 4
    assert db.query(Goal).filter(Goal.user_id == user.id, Goal.status == "active").one().type == "pay_off_debt"


def test_propose_goal_rejects_invalid_type(db, user):
    result = propose_goal(db, user.id, type="buy_a_yacht", target_amount=1000)
    assert "error" in result


def test_propose_goal_rejects_nonpositive_amount(db, user):
    result = propose_goal(db, user.id, type="save_amount", target_amount=0)
    assert "error" in result
