from datetime import date

from app.agent.tools import get_goal_progress
from app.services.goal_service import create_goal
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


def test_create_goal_before_any_sync_starts_at_zero(db, user):
    goal = create_goal(db, user.id, "save", target_amount=5000.0, target_date=date(2027, 1, 1))
    assert goal.type == "save"
    assert goal.name == "Savings"
    assert goal.starting_amount == 0.0
    assert goal.current_progress_amount == 0.0


def test_save_goal_progress_tracks_asset_growth(db, user):
    # Establish a baseline net worth snapshot, then set the goal against it.
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    goal = create_goal(db, user.id, "save", target_amount=1000.0, target_date=date(2027, 1, 1), name="Trip")
    assert goal.starting_amount == 2500.0  # total_assets at goal creation
    assert goal.name == "Trip"

    # Simulate the checking balance growing on the next sync.
    grown_accounts = FakeAggregatorClient()
    grown_accounts.accounts[0].current_balance = 3000.0  # +500 in assets
    sync_user_accounts(db, user.id, "fake-token", aggregator=grown_accounts)

    progress = get_goal_progress(db, user.id)
    assert progress["goals"][0]["current_progress_amount"] == 500.0
    assert progress["goals"][0]["progress_fraction"] == 0.5
    assert progress["goals"][0]["name"] == "Trip"


def test_legacy_pay_off_debt_alias_is_a_named_save_goal(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    goal = create_goal(db, user.id, "pay_off_debt", target_amount=800.0, target_date=date(2027, 1, 1))
    assert goal.type == "save"
    assert goal.name == "Paying off debt"
    assert goal.starting_amount == 2500.0  # total_assets, same as any save goal

    grown = FakeAggregatorClient()
    grown.accounts[0].current_balance = 2900.0  # +400 in assets
    sync_user_accounts(db, user.id, "fake-token", aggregator=grown)

    progress = get_goal_progress(db, user.id)
    assert progress["goals"][0]["current_progress_amount"] == 400.0
    assert progress["goals"][0]["progress_fraction"] == 0.5


def test_goal_completes_when_target_reached(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    create_goal(db, user.id, "save", target_amount=100.0, target_date=date(2027, 1, 1))

    grown = FakeAggregatorClient()
    grown.accounts[0].current_balance = 3000.0  # +500, well past the 100 target
    sync_user_accounts(db, user.id, "fake-token", aggregator=grown)

    from app.db.models import Goal

    goal = db.query(Goal).filter(Goal.user_id == user.id).one()
    assert goal.status == "completed"


def test_create_goal_adds_alongside_existing_up_to_five(db, user):
    first = create_goal(db, user.id, "save", 1000.0, date(2027, 1, 1), name="Trip")
    second = create_goal(db, user.id, "save", 8000.0, date(2027, 12, 31), name="Emergency fund")

    progress = get_goal_progress(db, user.id)
    assert progress["active_count"] == 2
    assert [g["id"] for g in progress["goals"]] == [str(first.id), str(second.id)]

    from app.services.goal_service import GoalLimitReached

    for i in range(3):
        create_goal(db, user.id, "save", 100.0 + i, None)

    assert get_goal_progress(db, user.id)["active_count"] == 5
    try:
        create_goal(db, user.id, "save", 50.0, None)
        raise AssertionError("expected GoalLimitReached")
    except GoalLimitReached:
        pass


def test_abandon_goal_removes_it_from_active_list_and_frees_a_slot(db, user):
    from app.services.goal_service import GoalLimitReached, abandon_goal

    goals = [create_goal(db, user.id, "save", 100.0 + i, None) for i in range(5)]
    try:
        create_goal(db, user.id, "save", 50.0, None)
        raise AssertionError("expected GoalLimitReached")
    except GoalLimitReached:
        pass

    dropped = abandon_goal(db, user.id, goals[0].id)
    assert dropped.status == "abandoned"
    remaining = get_goal_progress(db, user.id)
    assert remaining["active_count"] == 4
    assert str(goals[0].id) not in [g["id"] for g in remaining["goals"]]

    extra = create_goal(db, user.id, "save", 50.0, None)
    assert extra.status == "active"
    assert get_goal_progress(db, user.id)["active_count"] == 5


def test_track_spending_goal_progress_is_category_spend_this_month(db, user, monkeypatch):
    from datetime import datetime, timezone

    from app.services import money_query
    from app.services.goal_service import GoalValidationError

    monkeypatch.setattr(money_query, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())

    goal = create_goal(
        db, user.id, "track_spending", target_amount=0, target_date=None, category="eating out", window="this_month"
    )
    assert goal.category == "Dining"
    assert goal.window == "this_month"
    assert goal.name == "Dining"
    assert float(goal.current_progress_amount) == 45.0

    progress = get_goal_progress(db, user.id)
    tracker = progress["goals"][0]
    assert tracker["type"] == "track_spending"
    assert tracker["name"] == "Dining"
    assert tracker["category"] == "Dining"
    assert tracker["window"] == "this_month"
    assert tracker["current_progress_amount"] == 45.0
    assert tracker["target_amount"] == 0.0
    assert tracker["progress_fraction"] is None
    assert tracker["over_budget"] is False
    assert tracker["transaction_count"] == 1

    try:
        create_goal(db, user.id, "track_spending", 0, None, category=None, window="this_month")
        raise AssertionError("expected GoalValidationError")
    except GoalValidationError:
        pass


def test_track_spending_keeps_a_custom_name(db, user, monkeypatch):
    from datetime import datetime, timezone

    from app.services import money_query

    monkeypatch.setattr(money_query, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())

    goal = create_goal(
        db,
        user.id,
        "track_spending",
        target_amount=0,
        target_date=None,
        category="Dining",
        window="this_month",
        name="Eating out",
    )
    assert goal.name == "Eating out"
    assert get_goal_progress(db, user.id)["goals"][0]["name"] == "Eating out"


def test_track_spending_budget_marks_over_without_completing(db, user, monkeypatch):
    from datetime import datetime, timezone

    from app.db.models import Goal
    from app.services import money_query

    monkeypatch.setattr(money_query, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())

    create_goal(
        db, user.id, "track_spending", target_amount=20.0, target_date=None, category="Dining", window="this_month"
    )
    progress = get_goal_progress(db, user.id)["goals"][0]
    assert progress["current_progress_amount"] == 45.0
    assert progress["over_budget"] is True
    assert progress["progress_fraction"] == 2.25
    assert progress["remaining_amount"] == -25.0
    assert progress["on_pace"] is False
    assert progress["expected_progress_fraction"] == round(20 / 31, 4)

    goal = db.query(Goal).filter(Goal.user_id == user.id).one()
    assert goal.status == "active"


def test_track_spending_budget_shows_remaining_and_pace_through_the_month(db, user, monkeypatch):
    from datetime import datetime, timezone

    from app.services import money_query

    monkeypatch.setattr(money_query, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())

    create_goal(
        db, user.id, "track_spending", target_amount=500.0, target_date=None, category="Dining", window="this_month"
    )
    progress = get_goal_progress(db, user.id)["goals"][0]
    assert progress["remaining_amount"] == 455.0
    assert progress["progress_fraction"] == 0.09
    assert progress["expected_progress_fraction"] == round(20 / 31, 4)
    assert progress["on_pace"] is True
    assert progress["over_budget"] is False


def test_track_spending_ahead_of_pace_before_the_cap(db, user, monkeypatch):
    from datetime import datetime, timezone

    from app.services import money_query

    monkeypatch.setattr(money_query, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())

    # $45 spent of a $50 cap by Aug 20 is most of the budget with 11 days left.
    create_goal(
        db, user.id, "track_spending", target_amount=50.0, target_date=None, category="Dining", window="this_month"
    )
    progress = get_goal_progress(db, user.id)["goals"][0]
    assert progress["remaining_amount"] == 5.0
    assert progress["over_budget"] is False
    assert progress["on_pace"] is False
