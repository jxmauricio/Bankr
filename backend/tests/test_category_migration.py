"""Re-mapping stored transactions after the category table changes
(app/services/category_backfill.py), as the migrations that add or move
categories do."""

from app.db.models import Category, MerchantCategoryGuess, Transaction
from app.db.seed_categories import seed_default_categories
from app.services.category_backfill import remap_with_current_categories
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


def _txn(db, aggregator_id):
    return db.query(Transaction).filter(Transaction.aggregator_transaction_id == aggregator_id).one()


def _name(db, category_id):
    return db.get(Category, category_id).name


def test_a_re_map_puts_rows_back_where_plaid_says_except_the_users_picks(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    categories = seed_default_categories(db)
    picked, drifted = _txn(db, "txn_dining"), _txn(db, "txn_groceries")
    picked.bankr_category_id, picked.category_source = categories["travel_and_vacation"].id, "manual"
    drifted.bankr_category_id = categories["pets"].id
    db.commit()

    remap_with_current_categories(db)
    db.commit()
    db.expire_all()

    assert _name(db, _txn(db, "txn_dining").bankr_category_id) == "Travel & Vacation"  # the user's pick stays
    assert _name(db, _txn(db, "txn_groceries").bankr_category_id) == "Groceries"


def test_a_re_map_only_trusts_the_guesses_a_sync_would(db, user):
    """An unsure cached guess keeps Plaid's category, as on a sync."""
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    categories = seed_default_categories(db)
    for txn_id in ("txn_dining", "txn_groceries"):
        _txn(db, txn_id).aggregator_category_confidence = "LOW"
    db.add_all(
        [
            MerchantCategoryGuess(merchant_key="ramen spot", category_id=categories["coffee_shops"].id, source="jev", model="m", confidence=0.95),
            MerchantCategoryGuess(merchant_key="trader joe's", category_id=categories["pets"].id, source="jev", model="m", confidence=0.5),
        ]
    )
    db.commit()

    remap_with_current_categories(db)
    db.commit()
    db.expire_all()

    assert _name(db, _txn(db, "txn_dining").bankr_category_id) == "Coffee Shops"
    assert _name(db, _txn(db, "txn_groceries").bankr_category_id) == "Groceries"


def test_the_move_to_monarch_carries_picks_rules_budgets_and_trackers(db, user):
    """Rows of the Plaid-shaped tree (as c9e4a2f7d051 finds them) move to
    their Monarch successors: category_backfill.move_to_monarch."""
    from datetime import date

    from app.db.models import Budget, CategoryGroup, CategoryPref, Goal, Rule
    from app.services.category_backfill import move_to_monarch

    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    food = CategoryGroup(system_key="food_and_drink", name="Food & Drink", type="expense")
    db.add(food)
    db.flush()
    old = {}
    for key, name in (("restaurants", "Restaurants"), ("coffee", "Coffee"), ("software", "Software")):
        old[key] = Category(system_key=key, name=name, type="expense", group_id=food.id, is_system_default=True)
        db.add(old[key])
    db.flush()
    picked = _txn(db, "txn_dining")
    picked.bankr_category_id, picked.category_source = old["coffee"].id, "manual"
    db.add(Rule(user_id=user.id, merchant_contains="github", set_category_id=old["software"].id))
    db.add_all(
        [
            Budget(user_id=user.id, category_id=old["restaurants"].id, amount=100, group="flex", rollover=False, start_month=date(2026, 8, 1)),
            Budget(user_id=user.id, category_id=old["coffee"].id, amount=30, group="fixed", rollover=True, start_month=date(2026, 7, 1)),
            Budget(user_id=user.id, group_id=food.id, amount=500, group="flex", rollover=False, start_month=date(2026, 8, 1)),
            CategoryPref(user_id=user.id, group_id=food.id, budget_mode="by_category", name="Food"),
            CategoryPref(user_id=user.id, category_id=old["coffee"].id, name="Caffeine"),
            Goal(user_id=user.id, type="track_spending", target_amount=0, starting_amount=0, group_id=food.id, window="this_month"),
        ]
    )
    db.commit()

    move_to_monarch(db)
    db.commit()
    db.expire_all()

    categories = seed_default_categories(db)
    dining = db.query(CategoryGroup).filter(CategoryGroup.system_key == "food_and_dining").one()
    assert _name(db, _txn(db, "txn_dining").bankr_category_id) == "Coffee Shops"  # the user's pick, carried over
    assert db.query(Rule).one().set_category_id == categories["general_shopping"].id
    assert db.query(Goal).one().group_id == dining.id
    # The group budget moves to the new group; both category budgets land on
    # their successors (Coffee -> Coffee Shops, Restaurants -> Restaurants & Bars).
    by_target = {b.group_id or b.category_id: b for b in db.query(Budget)}
    assert float(by_target[dining.id].amount) == 500
    assert float(by_target[categories["coffee_shops"].id].amount) == 30
    assert float(by_target[categories["restaurants_and_bars"].id].amount) == 100
    # Budgeting by category carries over; names given to retired rows don't.
    pref = db.query(CategoryPref).one()
    assert (pref.group_id, pref.budget_mode, pref.name) == (dining.id, "by_category", None)
    assert not db.query(Category).filter(Category.system_key.in_(["restaurants", "coffee", "software"])).count()
    assert not db.query(CategoryGroup).filter(CategoryGroup.system_key == "food_and_drink").count()
