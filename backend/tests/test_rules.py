"""Categorization rules: applied on sync, to history on request, never over
a hand-picked category."""

from datetime import date

from app.agent import tools
from app.db.models import Category, CategoryGroup, Transaction
from app.db.seed_categories import seed_default_categories
from app.integrations.bank_aggregator import AggregatorTransaction
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


def _cat(db, name):
    """A category, or a group (Food & Drink), by name."""
    return db.query(Category).filter(Category.name == name).one_or_none() or db.query(CategoryGroup).filter(
        CategoryGroup.name == name
    ).one()


def _txn(db, aggregator_id) -> Transaction:
    return db.query(Transaction).filter(Transaction.aggregator_transaction_id == aggregator_id).one()


def _sync(db, user, fake):
    sync_user_accounts(db, user.id, "fake-token", aggregator=fake)
    db.expire_all()


def _ramen(txn_id, day, amount=-45.0):
    return AggregatorTransaction(txn_id, "acc_credit", amount, day, "Ramen Spot", "food_and_drink_restaurant", False)


def test_rule_applies_to_history_and_new_syncs(client, db, user):
    fake = FakeAggregatorClient(transactions_by_account={"acc_credit": [_ramen("r1", date(2026, 8, 1))]})
    _sync(db, user, fake)
    entertainment = _cat(db, "Entertainment & Recreation")

    preview = client.get("/rules/preview", params={"merchant_contains": "ramen", "category_id": str(entertainment.id)})
    assert preview.json() == {"would_change": 1}

    r = client.post(
        "/rules",
        json={
            "merchant_contains": "ramen",
            "set_category_id": str(entertainment.id),
            "set_merchant_name": "Ramen",
            "apply_to_existing": True,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["applied_to"] == 1
    assert r.json()["set_category"] == "Entertainment & Recreation"
    db.expire_all()
    assert _txn(db, "r1").bankr_category_id == entertainment.id
    assert _txn(db, "r1").merchant_name == "Ramen"

    # A re-sync re-maps r1 from Plaid's category, then the rule wins again;
    # a brand-new charge gets the rule too.
    fake.transactions_by_account["acc_credit"].append(_ramen("r2", date(2026, 8, 9)))
    _sync(db, user, fake)
    assert _txn(db, "r1").bankr_category_id == entertainment.id
    assert _txn(db, "r2").bankr_category_id == entertainment.id
    assert _txn(db, "r2").merchant_name == "Ramen"
    assert _txn(db, "r2").original_merchant_name == "Ramen Spot"


def test_rule_never_overrides_a_manual_category(client, db, user):
    fake = FakeAggregatorClient(transactions_by_account={"acc_credit": [_ramen("r1", date(2026, 8, 1))]})
    _sync(db, user, fake)
    shopping, entertainment = _cat(db, "Shopping"), _cat(db, "Entertainment & Recreation")
    client.patch(f"/transactions/{_txn(db, 'r1').id}", json={"category_id": str(shopping.id)})

    r = client.post(
        "/rules", json={"merchant_contains": "ramen", "set_category_id": str(entertainment.id), "apply_to_existing": True}
    )
    assert r.json()["applied_to"] == 0
    _sync(db, user, fake)
    assert _txn(db, "r1").bankr_category_id == shopping.id


def test_amount_bounds_and_priority(client, db, user):
    fake = FakeAggregatorClient(
        transactions_by_account={"acc_credit": [_ramen("small", date(2026, 8, 1), -12.0), _ramen("big", date(2026, 8, 2), -200.0)]}
    )
    _sync(db, user, fake)
    entertainment, travel = _cat(db, "Entertainment & Recreation"), _cat(db, "Travel & Vacation")
    client.post("/rules", json={"merchant_contains": "ramen", "set_category_id": str(entertainment.id)})
    client.post(
        "/rules",
        json={"merchant_contains": "ramen", "amount_min": 100, "set_category_id": str(travel.id), "priority": 5},
    )
    _sync(db, user, fake)
    assert _txn(db, "small").bankr_category_id == entertainment.id
    assert _txn(db, "big").bankr_category_id == travel.id


def test_rule_crud_and_validation(client, db, user):
    _sync(db, user, FakeAggregatorClient())
    entertainment = _cat(db, "Entertainment & Recreation")
    assert client.post("/rules", json={"merchant_contains": "x", "set_category_id": str(entertainment.id)}).status_code == 422
    rule = client.post("/rules", json={"merchant_contains": "Trader", "set_category_id": str(entertainment.id)}).json()
    assert client.get("/rules").json()["rules"][0]["id"] == rule["id"]
    edited = client.patch(f"/rules/{rule['id']}", json={"merchant_contains": "Trader Joe"}).json()
    assert edited["merchant_contains"] == "Trader Joe"
    assert client.delete(f"/rules/{rule['id']}").status_code == 204
    assert client.get("/rules").json()["rules"] == []


def test_propose_rule_tool_drafts_without_creating(db, user):
    _sync(db, user, FakeAggregatorClient())
    result = tools.propose_rule(db, user.id, merchant="Ramen", category="fun")
    assert result["status"] == "proposed"
    assert result["action"]["kind"] == "rule"
    assert result["action"]["category"] == "Entertainment & Recreation"
    assert result["action"]["would_change"] == 1
    assert tools.propose_rule(db, user.id, merchant="Ramen", category="nope").get("error")


def test_a_rule_cannot_put_a_merchant_on_a_group(client, db, user):
    seed_default_categories(db)
    db.commit()
    r = client.post("/rules", json={"merchant_contains": "ramen", "set_category_id": str(_cat(db, "Food & Dining").id)})
    assert r.status_code == 422
    assert "categories" in r.json()["detail"]
