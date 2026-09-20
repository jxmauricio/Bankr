from datetime import date

from app.agent.tools import propose_goal
from app.db.models import Goal
from app.services.goal_service import create_goal


def test_propose_goal_drafts_without_writing(db, user):
    result = propose_goal(db, user.id, type="save", target_amount=5000, target_date="2027-06-01")

    assert result["status"] == "proposed"
    assert result["proposal"] == {
        "type": "save",
        "name": "Savings",
        "target_amount": 5000.0,
        "target_date": "2027-06-01",
        "category": None,
        "window": None,
        "replaces_existing": False,
        "at_limit": False,
        "active_count": 0,
        "slots_remaining": 5,
    }
    assert db.query(Goal).filter(Goal.user_id == user.id).count() == 0


def test_propose_goal_uses_name_and_legacy_type_as_title(db, user):
    named = propose_goal(db, user.id, type="save", name="Trip to Japan", target_amount=4000)
    assert named["proposal"]["type"] == "save"
    assert named["proposal"]["name"] == "Trip to Japan"

    legacy = propose_goal(db, user.id, type="build_emergency_fund", target_amount=8000)
    assert legacy["proposal"]["type"] == "save"
    assert legacy["proposal"]["name"] == "Emergency fund"


def test_propose_goal_adds_alongside_an_active_goal(db, user):
    create_goal(db, user.id, "save", 2000.0, date(2027, 1, 1), name="Paying off debt")

    result = propose_goal(db, user.id, type="save", name="Emergency fund", target_amount=8000)

    assert result["proposal"]["replaces_existing"] is False
    assert result["proposal"]["at_limit"] is False
    assert result["proposal"]["active_count"] == 1
    assert result["proposal"]["slots_remaining"] == 4
    assert db.query(Goal).filter(Goal.user_id == user.id, Goal.status == "active").one().type == "save"


def test_propose_goal_rejects_invalid_type(db, user):
    result = propose_goal(db, user.id, type="buy_a_yacht", target_amount=1000)
    assert "error" in result


def test_propose_goal_rejects_nonpositive_amount(db, user):
    result = propose_goal(db, user.id, type="save", target_amount=0)
    assert "error" in result


def test_propose_goal_drafts_a_spending_tracker(db, user):
    result = propose_goal(
        db, user.id, type="track_spending", category="eating out", window="this_month"
    )

    assert result["status"] == "proposed"
    assert result["proposal"]["type"] == "track_spending"
    assert result["proposal"]["name"] == "Dining"
    assert result["proposal"]["category"] == "Dining"
    assert result["proposal"]["window"] == "this_month"
    assert result["proposal"]["target_amount"] == 0.0
    assert result["proposal"]["target_date"] is None
    assert db.query(Goal).filter(Goal.user_id == user.id).count() == 0


def test_propose_goal_spending_tracker_keeps_optional_name_and_cap(db, user):
    result = propose_goal(
        db,
        user.id,
        type="track_spending",
        name="Coffee budget",
        category="Groceries",
        window="this_week",
        target_amount=200,
    )
    assert result["proposal"]["name"] == "Coffee budget"
    assert result["proposal"]["target_amount"] == 200.0
    assert result["proposal"]["window"] == "this_week"


def test_propose_goal_spending_tracker_defaults_window(db, user):
    result = propose_goal(db, user.id, type="track_spending", category="Coffee")
    assert result["proposal"]["window"] == "this_month"
    assert result["proposal"]["name"] == "Coffee"


def test_propose_goal_rejects_unknown_tracker_category(db, user):
    result = propose_goal(db, user.id, type="track_spending", category="yachts")
    assert "error" in result


def test_propose_goal_rejects_unknown_tracker_window(db, user):
    result = propose_goal(db, user.id, type="track_spending", category="Dining", window="last_month")
    assert "error" in result
