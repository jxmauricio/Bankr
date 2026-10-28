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
    picked.bankr_category_id, picked.category_overridden = categories["travel"].id, True
    drifted.bankr_category_id = categories["pets"].id
    db.commit()

    remap_with_current_categories(db)
    db.commit()
    db.expire_all()

    assert _name(db, _txn(db, "txn_dining").bankr_category_id) == "Travel"  # the user's pick stays
    assert _name(db, _txn(db, "txn_groceries").bankr_category_id) == "Groceries"


def test_a_re_map_only_trusts_the_guesses_a_sync_would(db, user):
    """An unsure cached guess keeps Plaid's category, as on a sync."""
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    categories = seed_default_categories(db)
    for txn_id in ("txn_dining", "txn_groceries"):
        _txn(db, txn_id).aggregator_category_confidence = "LOW"
    db.add_all(
        [
            MerchantCategoryGuess(merchant_key="ramen spot", category_id=categories["coffee"].id, source="jev", model="m", confidence=0.95),
            MerchantCategoryGuess(merchant_key="trader joe's", category_id=categories["pets"].id, source="jev", model="m", confidence=0.5),
        ]
    )
    db.commit()

    remap_with_current_categories(db)
    db.commit()
    db.expire_all()

    assert _name(db, _txn(db, "txn_dining").bankr_category_id) == "Coffee"
    assert _name(db, _txn(db, "txn_groceries").bankr_category_id) == "Groceries"
