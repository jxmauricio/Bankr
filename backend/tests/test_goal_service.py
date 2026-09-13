from datetime import date

from app.agent.tools import get_goal_progress
from app.services.goal_service import create_goal
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


def test_create_goal_before_any_sync_starts_at_zero(db, user):
    goal = create_goal(db, user.id, "save_amount", target_amount=5000.0, target_date=date(2027, 1, 1))
    assert goal.starting_amount == 0.0
    assert goal.current_progress_amount == 0.0


def test_save_amount_goal_progress_tracks_asset_growth(db, user):
    # Establish a baseline net worth snapshot, then set the goal against it.
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    goal = create_goal(db, user.id, "save_amount", target_amount=1000.0, target_date=date(2027, 1, 1))
    assert goal.starting_amount == 2500.0  # total_assets at goal creation

    # Simulate the checking balance growing on the next sync.
    grown_accounts = FakeAggregatorClient()
    grown_accounts.accounts[0].current_balance = 3000.0  # +500 in assets
    sync_user_accounts(db, user.id, "fake-token", aggregator=grown_accounts)

    progress = get_goal_progress(db, user.id)
    assert progress["goals"][0]["current_progress_amount"] == 500.0
    assert progress["goals"][0]["progress_fraction"] == 0.5


def test_pay_off_debt_goal_progress_tracks_liability_reduction(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    goal = create_goal(db, user.id, "pay_off_debt", target_amount=400.0, target_date=date(2027, 1, 1))
    assert goal.starting_amount == 400.0  # total_liabilities at goal creation

    paid_down = FakeAggregatorClient()
    paid_down.accounts[1].current_balance = 100.0  # credit balance drops from 400 to 100
    sync_user_accounts(db, user.id, "fake-token", aggregator=paid_down)

    progress = get_goal_progress(db, user.id)
    assert progress["goals"][0]["current_progress_amount"] == 300.0
    assert progress["goals"][0]["progress_fraction"] == 0.75


def test_goal_completes_when_target_reached(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    create_goal(db, user.id, "save_amount", target_amount=100.0, target_date=date(2027, 1, 1))

    grown = FakeAggregatorClient()
    grown.accounts[0].current_balance = 3000.0  # +500, well past the 100 target
    sync_user_accounts(db, user.id, "fake-token", aggregator=grown)

    from app.db.models import Goal

    goal = db.query(Goal).filter(Goal.user_id == user.id).one()
    assert goal.status == "completed"


def test_create_goal_adds_alongside_existing_up_to_five(db, user):
    first = create_goal(db, user.id, "save_amount", 1000.0, date(2027, 1, 1))
    second = create_goal(db, user.id, "build_emergency_fund", 8000.0, date(2027, 12, 31))

    progress = get_goal_progress(db, user.id)
    assert progress["active_count"] == 2
    assert [g["id"] for g in progress["goals"]] == [str(first.id), str(second.id)]

    from app.services.goal_service import GoalLimitReached

    for i in range(3):
        create_goal(db, user.id, "save_amount", 100.0 + i, None)

    assert get_goal_progress(db, user.id)["active_count"] == 5
    try:
        create_goal(db, user.id, "save_amount", 50.0, None)
        raise AssertionError("expected GoalLimitReached")
    except GoalLimitReached:
        pass
