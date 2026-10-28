"""Built-in categories are found by key, never by name: renaming one moves
nothing. See app/db/seed_categories.py."""

from datetime import date

from app.db import seed_categories
from app.db.models import Budget, Category, Transaction
from app.db.seed_categories import category_color, seed_default_categories
from app.services import money_query as mq
from app.services.sync_service import sync_user_accounts
from app.services.transaction_edit_service import category_tree
from tests.fake_aggregator import FakeAggregatorClient


def _rename_default(monkeypatch, key, name):
    monkeypatch.setattr(
        seed_categories,
        "DEFAULT_CATEGORIES",
        [(k, name if k == key else n, t, p) for k, n, t, p in seed_categories.DEFAULT_CATEGORIES],
    )


def test_renaming_a_built_in_keeps_its_row_mapping_budget_and_color(db, user, monkeypatch):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    restaurants = seed_default_categories(db)["restaurants"]
    ramen = db.query(Transaction).filter(Transaction.aggregator_transaction_id == "txn_dining").one()
    assert ramen.bankr_category_id == restaurants.id
    food = seed_default_categories(db)["food_and_drink"]
    db.add(Budget(user_id=user.id, category_id=food.id, amount=300, group="flex", rollover=False, start_month=date(2026, 8, 1)))
    db.commit()
    color = category_color(restaurants)

    _rename_default(monkeypatch, "restaurants", "Dining Out")
    renamed = seed_default_categories(db)["restaurants"]
    db.commit()

    assert renamed.id == restaurants.id and renamed.name == "Dining Out"
    assert db.query(Category).filter(Category.name == "Restaurants").count() == 0
    assert category_color(renamed) == color
    # A fresh sync still lands the ramen there, and questions find it by its new name, key or alias.
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    assert db.query(Transaction).filter(Transaction.aggregator_transaction_id == "txn_dining").one().bankr_category_id == renamed.id
    for asked in ("Dining Out", "restaurants", "takeout"):
        assert mq.resolve_category(db, asked, user.id).category_id == renamed.id
    assert db.query(Budget).one().category_id == food.id


def test_the_category_tree_carries_keys_and_colors(db, user):
    tree = {node["key"]: node for node in category_tree(db, user.id)}
    food = tree["food_and_drink"]
    assert food["color"].startswith("#")
    assert {child["key"] for child in food["children"]} >= {"groceries", "restaurants", "coffee"}


def test_slices_resolve_by_name_or_key(db, user):
    by_name = mq.resolve_category(db, "Eating Out", user.id)
    assert by_name.slice == "eating_out" and by_name.category_id is None
    assert mq.resolve_category(db, "eating_out", user.id).ids == by_name.ids
