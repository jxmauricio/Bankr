"""Built-in categories are found by key, never by name: renaming one moves
nothing. See app/db/seed_categories.py."""

from datetime import date

from app.db import seed_categories
from app.db.models import Budget, Category, Transaction
from app.db.seed_categories import category_color, seed_default_categories, seed_default_groups
from app.services import money_query as mq
from app.services.sync_service import sync_user_accounts
from app.services.transaction_edit_service import category_tree
from tests.fake_aggregator import FakeAggregatorClient


def _rename_default(monkeypatch, key, name):
    monkeypatch.setattr(
        seed_categories,
        "DEFAULT_CATEGORIES",
        [(k, name if k == key else n, t, g, e) for k, n, t, g, e in seed_categories.DEFAULT_CATEGORIES],
    )


def test_renaming_a_built_in_keeps_its_row_mapping_budget_and_color(db, user, monkeypatch):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    restaurants = seed_default_categories(db)["restaurants_and_bars"]
    ramen = db.query(Transaction).filter(Transaction.aggregator_transaction_id == "txn_dining").one()
    assert ramen.bankr_category_id == restaurants.id
    food = seed_default_groups(db)["food_and_dining"]
    db.add(Budget(user_id=user.id, group_id=food.id, amount=300, group="flex", rollover=False, start_month=date(2026, 8, 1)))
    db.commit()
    color = category_color(restaurants)

    _rename_default(monkeypatch, "restaurants_and_bars", "Dining Out")
    renamed = seed_default_categories(db)["restaurants_and_bars"]
    db.commit()

    assert renamed.id == restaurants.id and renamed.name == "Dining Out"
    assert db.query(Category).filter(Category.name == "Restaurants & Bars").count() == 0
    assert category_color(renamed) == color
    # A fresh sync still lands the ramen there, and questions find it by its new name, key or alias.
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    assert db.query(Transaction).filter(Transaction.aggregator_transaction_id == "txn_dining").one().bankr_category_id == renamed.id
    for asked in ("Dining Out", "restaurants_and_bars", "takeout"):
        assert mq.resolve_category(db, asked, user.id).category_id == renamed.id
    assert db.query(Budget).one().group_id == food.id


def test_the_category_tree_carries_keys_and_colors(db, user):
    tree = {node["key"]: node for node in category_tree(db, user.id)}
    food = tree["food_and_dining"]
    assert food["color"].startswith("#")
    assert {child["key"] for child in food["children"]} == {"groceries", "restaurants_and_bars", "coffee_shops"}


def test_slices_resolve_by_name_or_key(db, user):
    by_name = mq.resolve_category(db, "Eating Out", user.id)
    assert by_name.slice == "eating_out" and by_name.category_id is None
    assert mq.resolve_category(db, "eating_out", user.id).ids == by_name.ids


def test_a_user_renames_a_built_in_for_themselves_only(client, db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    restaurants = seed_default_categories(db)["restaurants_and_bars"]
    food = seed_default_groups(db)["food_and_dining"]
    for item, name in ((restaurants, "Dining Out"), (food, "Food")):
        assert client.patch(f"/categories/{item.id}", json={"name": name}).status_code == 200

    # Their name everywhere they look, and in what they can ask by...
    row = next(t for t in client.get("/dashboard/transactions?start=2026-08-01&end=2026-08-31").json()["transactions"] if t["merchant_name"] == "Ramen Spot")
    assert (row["category"], row["parent_category"]) == ("Dining Out", "Food")
    assert mq.resolve_category(db, "dining out", user.id).category_id == restaurants.id
    assert mq.resolve_category(db, "Food", user.id).group_id == food.id
    # ...while the row, and everyone else, keep the built-in name.
    db.expire_all()
    assert db.get(Category, restaurants.id).name == "Restaurants & Bars"
    assert mq.resolve_category(db, "Restaurants & Bars").category_id == restaurants.id

    # An empty name puts the built-in one back.
    client.patch(f"/categories/{restaurants.id}", json={"name": ""})
    assert mq.resolve_category(db, "restaurants", user.id).name == "Restaurants & Bars"


def test_a_group_can_be_budgeted_by_category(client, db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    client.put("/budgets/settings", json={"mode": "category"})  # a line per budget, not a Flexible pool
    food = seed_default_groups(db)["food_and_dining"]
    restaurants = seed_default_categories(db)["restaurants_and_bars"]
    assert client.put(f"/budgets/{restaurants.id}", json={"amount": 100}).status_code == 422  # budgeted by group

    r = client.put(f"/budgets/groups/{food.id}/mode", json={"mode": "by_category"})
    assert r.status_code == 200, r.text
    assert client.put(f"/budgets/{restaurants.id}", json={"amount": 100}).status_code == 200
    line = next(line for line in client.get("/budgets").json()["lines"] if line["name"] == "Restaurants & Bars")
    assert (line["kind"], line["budgeted"]) == ("category", 100.0)
    assert {n["budget_mode"] for n in client.get("/categories").json()["categories"] if n["group_id"] == str(food.id)} == {
        "by_category"
    }
