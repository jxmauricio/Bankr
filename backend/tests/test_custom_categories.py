"""Categories a user makes for themselves (app/services/category_service.py):
theirs alone, kept to the two-level tree, and undone cleanly on delete."""

from datetime import date, datetime, timezone

import pytest

from app.db.models import Budget, Category, Goal, Rule, Transaction, User
from app.services import money_query as mq
from app.services.account_removal import delete_user
from app.services.category_service import CategoryError, create_category, delete_category
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))


def _cat(db, name) -> Category:
    return db.query(Category).filter(Category.name == name).one()


def _txn(db, aggregator_id) -> Transaction:
    return db.query(Transaction).filter(Transaction.aggregator_transaction_id == aggregator_id).one()


def _synced(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())


def _other_user(db) -> User:
    other = User(email="other@example.com", apple_sub="other")
    db.add(other)
    db.commit()
    return other


def test_a_subcategory_of_ones_own_counts_in_its_group(client, db, user):
    _synced(db, user)
    shopping = _cat(db, "General Merchandise")

    r = client.post("/categories", json={"name": "  Ramen   Nights ", "parent_id": str(shopping.id)})
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Ramen Nights"  # tidied
    ramen = r.json()["id"]
    assert client.patch(f"/transactions/{_txn(db, 'txn_dining').id}", json={"category_id": ramen}).status_code == 200

    # The assistant finds it by name, and the group's total includes it.
    window = mq.resolve_window(date(2026, 8, 20), "this_month")
    assert mq.spend_query(db, user.id, window, mq.resolve_category(db, "ramen nights", user.id))["total_spent"] == 45.0
    assert mq.spend_query(db, user.id, window, mq.resolve_category(db, "General Merchandise", user.id))["total_spent"] == 45.0

    tree = client.get("/categories").json()["categories"]
    group = next(c for c in tree if c["name"] == "General Merchandise")
    assert {"name": "Ramen Nights", "custom": True} in [{"name": c["name"], "custom": c["custom"]} for c in group["children"]]
    assert group["custom"] is False


def test_a_top_level_one_can_have_its_own_budget(client, db, user):
    _synced(db, user)
    wedding = client.post("/categories", json={"name": "Wedding"}).json()

    r = client.put(f"/budgets/{wedding['id']}", json={"amount": 2000})
    assert r.status_code == 200, r.text
    assert db.query(Budget).filter(Budget.user_id == user.id).one().category_id == _cat(db, "Wedding").id


def test_the_tree_keeps_two_levels_and_unique_names(client, db, user):
    _synced(db, user)
    travel = _cat(db, "Travel")  # a leaf: a child would make it a group with rows on it
    groceries = _cat(db, "Groceries")
    mine = client.post("/categories", json={"name": "Hobbies"}).json()

    for body in (
        {"name": "Trips", "parent_id": str(travel.id)},
        {"name": "Organic", "parent_id": str(groceries.id)},
        {"name": "Models", "parent_id": mine["id"]},
        {"name": "coffee"},  # a built-in name
        {"name": "HOBBIES"},  # one of mine
        {"name": "Eating Out"},  # what "eating out" already means
        {"name": "   "},
        {"name": "x" * 41},
    ):
        r = client.post("/categories", json=body)
        assert r.status_code == 422, body


def test_another_users_category_is_invisible_to_them(client, db, user):
    _synced(db, user)
    other = _other_user(db)
    theirs = create_category(db, other.id, "Their Secret")
    db.commit()

    assert "Their Secret" not in str(client.get("/categories").json())
    txn = _txn(db, "txn_dining")
    assert client.patch(f"/transactions/{txn.id}", json={"category_id": str(theirs.id)}).status_code == 422
    r = client.post("/rules", json={"merchant_contains": "ramen", "set_category_id": str(theirs.id)})
    assert r.status_code == 422
    assert client.put(f"/budgets/{theirs.id}", json={"amount": 5}).status_code == 422
    assert client.patch(f"/categories/{theirs.id}", json={"name": "Mine now"}).status_code == 404
    assert client.delete(f"/categories/{theirs.id}").status_code == 404
    with pytest.raises(mq.QueryError):
        mq.resolve_category(db, "Their Secret", user.id)
    # And it doesn't take the name from anyone else.
    assert create_category(db, user.id, "Their Secret").name == "Their Secret"


def test_renaming_carries_the_tracker_along(client, db, user):
    _synced(db, user)
    hobbies = client.post("/categories", json={"name": "Hobbies"}).json()
    r = client.post("/goals", json={"type": "track_spending", "category": "hobbies", "window": "this_month"})
    assert r.status_code == 200, r.text

    assert client.patch(f"/categories/{hobbies['id']}", json={"name": "Crafts"}).json()["name"] == "Crafts"
    assert db.query(Goal).one().category == "Crafts"
    # A tracker follows it, so it can't simply vanish.
    assert client.delete(f"/categories/{hobbies['id']}").status_code == 422


def test_deleting_one_sends_its_rows_back_to_plaids_category(client, db, user):
    _synced(db, user)
    ramen = create_category(db, user.id, "Ramen Nights", _cat(db, "Food & Drink").id)
    db.commit()
    client.patch(f"/transactions/{_txn(db, 'txn_dining').id}", json={"category_id": str(ramen.id)})
    client.post("/rules", json={"merchant_contains": "trader", "set_category_id": str(ramen.id), "apply_to_existing": True})
    assert _txn(db, "txn_groceries").bankr_category_id == ramen.id

    r = client.delete(f"/categories/{ramen.id}")
    assert r.status_code == 200, r.text
    assert r.json() == {"recategorized": 2}
    db.expire_all()

    dining, groceries = _txn(db, "txn_dining"), _txn(db, "txn_groceries")
    assert dining.category.name == "Restaurants" and not dining.category_overridden
    assert groceries.category.name == "Groceries"
    assert db.query(Rule).count() == 0
    assert db.query(Category).filter(Category.user_id == user.id).count() == 0


def test_deleting_the_user_takes_their_categories(db, user):
    _synced(db, user)
    hobbies = create_category(db, user.id, "Hobbies")
    _txn(db, "txn_dining").bankr_category_id = hobbies.id
    db.add(Rule(user_id=user.id, merchant_contains="ramen", set_category_id=hobbies.id))
    db.add(Budget(user_id=user.id, category_id=hobbies.id, amount=100, group="flex", rollover=False, start_month=date(2026, 8, 1)))
    db.commit()

    delete_user(db, user.id, FakeAggregatorClient())

    assert db.query(Category).filter(Category.user_id.isnot(None)).count() == 0


def test_only_so_many(db, user):
    import app.services.category_service as service

    for n in range(service.MAX_CUSTOM_CATEGORIES):
        create_category(db, user.id, f"Mine {n}")
    with pytest.raises(CategoryError):
        create_category(db, user.id, "One more")
    with pytest.raises(LookupError):
        delete_category(db, user.id, _cat(db, "Travel").id)  # a built-in one isn't theirs to delete
