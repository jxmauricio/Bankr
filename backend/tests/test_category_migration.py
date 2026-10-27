"""Moving a database from the legacy category tree to Plaid's 16 primaries
(app/services/category_backfill.py, migration c8e1f5a2d697)."""

from datetime import date

from app.db.models import Budget, Category, Goal, Rule, Transaction
from app.services.category_backfill import move_to_plaid_primaries
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


def _legacy(db, name, type_="expense", parent=None):
    category = Category(name=name, type=type_, is_system_default=True, parent_category_id=parent and parent.id)
    db.add(category)
    db.flush()
    return category


def _txn(db, aggregator_id):
    return db.query(Transaction).filter(Transaction.aggregator_transaction_id == aggregator_id).one()


def _name(db, category_id):
    return db.get(Category, category_id).name


def test_everything_on_a_legacy_category_moves_to_its_new_one(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    dining = _legacy(db, "Dining")
    restaurants = _legacy(db, "Restaurants", parent=dining)
    housing = _legacy(db, "Rent & Housing")
    shopping = _legacy(db, "Shopping")
    transfer = _legacy(db, "Transfer", "transfer")

    # As the old code left them: Trader Joe's on a legacy category, the
    # user's own picks for the other two.
    _txn(db, "txn_groceries").bankr_category_id = housing.id
    ramen = _txn(db, "txn_dining")
    ramen.bankr_category_id, ramen.category_overridden = restaurants.id, True
    paycheck = db.query(Transaction).filter(Transaction.merchant_name == "Employer Inc").one()
    paycheck.bankr_category_id, paycheck.category_overridden = transfer.id, True
    db.add(Rule(user_id=user.id, merchant_contains="trader", set_category_id=shopping.id))
    db.add_all(
        [
            Budget(user_id=user.id, category_id=restaurants.id, amount=400, group="flex", rollover=False, start_month=date(2026, 8, 1)),
            Budget(user_id=user.id, category_id=dining.id, amount=200, group="fixed", rollover=True, start_month=date(2026, 7, 1)),
        ]
    )
    db.add(Goal(user_id=user.id, type="track_spending", target_amount=0, starting_amount=0, category="Dining", window="this_month"))
    db.commit()

    move_to_plaid_primaries(db)
    db.commit()
    db.expire_all()

    assert _name(db, _txn(db, "txn_dining").bankr_category_id) == "Food & Drink"  # the user's pick, carried over
    assert _name(db, paycheck.bankr_category_id) == "Transfer In"  # money in, so the in side
    assert _name(db, _txn(db, "txn_groceries").bankr_category_id) == "General Merchandise"  # the rule still wins
    assert _name(db, db.query(Rule).one().set_category_id) == "General Merchandise"

    (budget,) = db.query(Budget).all()
    assert _name(db, budget.category_id) == "Food & Drink"
    assert (float(budget.amount), budget.group, budget.rollover, budget.start_month) == (600.0, "fixed", True, date(2026, 7, 1))

    assert db.query(Goal).one().category == "Food & Drink"
    names = {c.name for c in db.query(Category)}
    assert not names & {"Dining", "Restaurants", "Rent & Housing", "Shopping", "Transfer"}
    assert len(names) == 22  # the 16 primaries and their 6 subcategories


def test_a_legacy_name_that_is_a_category_again_keeps_its_rows(db, user):
    """Groceries was top-level before the move and is a subcategory of Food
    & Drink after it: same row, re-parented, nothing moved off it."""
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    groceries = db.query(Category).filter(Category.name == "Groceries").one()
    groceries.parent_category_id = None  # top-level, as the legacy tree had it
    db.commit()
    move_to_plaid_primaries(db)
    db.commit()
    db.expire_all()
    assert db.get(Category, groceries.id).parent_category_id is not None
    assert _txn(db, "txn_groceries").bankr_category_id == groceries.id


def test_running_it_again_changes_nothing(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    before = {t.id: t.bankr_category_id for t in db.query(Transaction)}
    move_to_plaid_primaries(db)
    db.commit()
    assert {t.id: t.bankr_category_id for t in db.query(Transaction)} == before
