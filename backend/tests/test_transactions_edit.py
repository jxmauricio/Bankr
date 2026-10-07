"""Editing, excluding and splitting transactions -- and that a re-sync
never undoes the user's edits."""

from datetime import date

from app.db.models import Category, Transaction
from app.integrations.bank_aggregator import AggregatorTransaction
from app.services import money_query as mq
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient

AUG = mq.Window(date(2026, 8, 1), date(2026, 8, 31), "custom")


def _sync(db, user, fake=None):
    fake = fake or FakeAggregatorClient()
    sync_user_accounts(db, user.id, "fake-token", aggregator=fake)
    return fake


def _txn(db, aggregator_id) -> Transaction:
    return db.query(Transaction).filter(Transaction.aggregator_transaction_id == aggregator_id).one()


def _cat(db, name) -> Category:
    return db.query(Category).filter(Category.name == name).one()


def test_recategorize_survives_resync(client, db, user):
    fake = _sync(db, user)
    txn = _txn(db, "txn_dining")
    shopping = _cat(db, "Shopping")

    r = client.patch(f"/transactions/{txn.id}", json={"category_id": str(shopping.id), "merchant_name": "Ramen!"})
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "Shopping"
    assert r.json()["merchant_name"] == "Ramen!"

    _sync(db, user, fake)  # the fake re-reports every row, like Plaid's "modified"
    db.expire_all()
    txn = _txn(db, "txn_dining")
    assert txn.bankr_category_id == shopping.id
    assert txn.merchant_name == "Ramen!"
    assert txn.original_merchant_name == "Ramen Spot"


def test_clearing_rename_restores_bank_name(client, db, user):
    _sync(db, user)
    txn = _txn(db, "txn_dining")
    client.patch(f"/transactions/{txn.id}", json={"merchant_name": "Ramen!"})
    r = client.patch(f"/transactions/{txn.id}", json={"merchant_name": "  "})
    assert r.json()["merchant_name"] == "Ramen Spot"


def test_excluded_rows_drop_out_of_spending(client, db, user):
    _sync(db, user)
    assert mq.spend_query(db, user.id, AUG)["total_spent"] == 165.50
    txn = _txn(db, "txn_dining")
    r = client.patch(f"/transactions/{txn.id}", json={"excluded": True, "notes": "work dinner"})
    assert r.json()["is_excluded"] is True and r.json()["notes"] == "work dinner"
    assert mq.spend_query(db, user.id, AUG)["total_spent"] == 120.50
    # Still listed, flagged.
    listed = {t["id"]: t for t in mq.list_transactions(db, user.id, AUG)["transactions"]}
    assert listed[str(txn.id)]["is_excluded"] is True


def test_split_moves_spending_between_categories(client, db, user):
    _sync(db, user)
    txn = _txn(db, "txn_groceries")  # -120.50 Groceries
    shopping = _cat(db, "Shopping")
    groceries = _cat(db, "Groceries")

    r = client.put(
        f"/transactions/{txn.id}/splits",
        json={
            "splits": [
                {"amount": -100.50, "category_id": str(groceries.id)},
                {"amount": -20.00, "category_id": str(shopping.id), "note": "batteries"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_split"] is True
    assert [s["amount"] for s in body["splits"]] == [-100.50, -20.00]

    spend = mq.spend_query(db, user.id, AUG, group_by="category")
    assert spend["total_spent"] == 165.50  # unchanged overall
    groups = {g["name"]: g["amount"] for g in spend["groups"]}
    assert groups["Groceries"] == 100.50
    assert groups["Shopping"] == 20.00

    # Children nest under the parent instead of being listed twice.
    rows = mq.list_transactions(db, user.id, AUG)["transactions"]
    assert len(rows) == 3

    # A re-sync keeps the split.
    _sync(db, user)
    db.expire_all()
    assert mq.spend_query(db, user.id, AUG)["total_spent"] == 165.50

    # Removing it restores the original.
    r = client.put(f"/transactions/{txn.id}/splits", json={"splits": []})
    assert r.json()["is_split"] is False
    groups = {g["name"]: g["amount"] for g in mq.spend_query(db, user.id, AUG, group_by="category")["groups"]}
    assert groups["Groceries"] == 120.50


def test_split_must_add_up(client, db, user):
    _sync(db, user)
    txn = _txn(db, "txn_groceries")
    groceries = _cat(db, "Groceries")
    r = client.put(
        f"/transactions/{txn.id}/splits",
        json={
            "splits": [
                {"amount": -100, "category_id": str(groceries.id)},
                {"amount": -10, "category_id": str(groceries.id)},
            ]
        },
    )
    assert r.status_code == 422
    db.expire_all()
    assert _txn(db, "txn_groceries").is_split is False


def test_edits_follow_a_pending_charge_when_it_posts(client, db, user):
    pending = AggregatorTransaction("p1", "acc_credit", -30.0, date(2026, 8, 6), "Cafe", "food_and_drink_coffee", True)
    fake = FakeAggregatorClient(transactions_by_account={"acc_credit": [pending]})
    _sync(db, user, fake)
    shopping = _cat(db, "Shopping")
    client.patch(f"/transactions/{_txn(db, 'p1').id}", json={"category_id": str(shopping.id)})

    posted = AggregatorTransaction(
        "posted1", "acc_credit", -30.0, date(2026, 8, 7), "Cafe", "food_and_drink_coffee", False,
        pending_transaction_id="p1",
    )
    fake.transactions_by_account = {"acc_credit": [posted]}
    fake.removed_ids = ["p1"]
    _sync(db, user, fake)
    db.expire_all()
    assert db.query(Transaction).filter(Transaction.aggregator_transaction_id == "p1").count() == 0
    assert _txn(db, "posted1").bankr_category_id == shopping.id


def test_cannot_edit_someone_elses_transaction(client, db, user):
    from uuid import uuid4

    from app.db.models import User

    other = User(email=f"{uuid4()}@example.com", apple_sub=str(uuid4()))
    db.add(other)
    db.commit()
    sync_user_accounts(db, other.id, "other-token", aggregator=FakeAggregatorClient(
        transactions_by_account={"acc_credit": [
            AggregatorTransaction("theirs", "acc_credit", -5.0, date(2026, 8, 1), "X", None, False)
        ]},
    ))
    r = client.patch(f"/transactions/{_txn(db, 'theirs').id}", json={"notes": "hi"})
    assert r.status_code == 404


def test_categories_tree(client, db, user):
    _sync(db, user)
    cats = client.get("/categories").json()["categories"]
    dining = next(c for c in cats if c["name"] == "Dining")
    assert {"Coffee", "Restaurants"} <= {c["name"] for c in dining["children"]}
    assert cats[0]["type"] == "expense"
