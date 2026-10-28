"""Where a transaction lands, and why (app/services/categorization_service.py):
the user's pick, then their rules, then what they taught it, then Plaid
(with a second opinion when Plaid isn't sure), else Uncategorized. And the
categories a user hides or excludes."""

from datetime import date

from app.db.models import Category, LearnedCategory, Rule, Transaction
from app.db.seed_categories import seed_default_categories
from app.integrations.bank_aggregator import AggregatorTransaction
from app.services import money_query as mq
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


def _t(txn_id, amount, merchant, raw, day=date(2026, 8, 12)):
    return AggregatorTransaction(txn_id, "acc_checking", amount, day, merchant, raw, False)


def _sync(db, user, *txns):
    sync_user_accounts(
        db, user.id, "fake-token", aggregator=FakeAggregatorClient(transactions_by_account={"acc_checking": list(txns)})
    )


def _row(db, txn_id):
    return db.query(Transaction).filter(Transaction.aggregator_transaction_id == txn_id).one()


def _where(db, txn_id):
    row = _row(db, txn_id)
    return row.category.name, row.category_source


def test_each_row_says_where_its_category_came_from(db, user):
    categories = seed_default_categories(db)
    db.add(Rule(user_id=user.id, merchant_contains="blue bottle", set_category_id=categories["groceries"].id))
    db.commit()
    _sync(
        db,
        user,
        _t("plaid", -12.0, "Chipotle", "FOOD_AND_DRINK_FAST_FOOD"),
        _t("rule", -5.0, "Blue Bottle", "FOOD_AND_DRINK_COFFEE"),
        _t("nothing", -9.0, "SQ *MYSTERY", None),
    )
    assert _where(db, "plaid") == ("Restaurants & Bars", "aggregator")
    assert _where(db, "rule") == ("Groceries", "rule")
    assert _where(db, "nothing") == ("Uncategorized", "fallback")


def test_two_matching_picks_teach_the_merchant(client, db, user):
    rows = [_t(f"tj{n}", -40.0, "Trader Joe's", "GENERAL_MERCHANDISE_SUPERSTORES", date(2026, 8, n)) for n in (1, 2, 3)]
    _sync(db, user, *rows)
    groceries = seed_default_categories(db)["groceries"]
    assert _where(db, "tj3") == ("Shopping", "aggregator")

    client.patch(f"/transactions/{_row(db, 'tj1').id}", json={"category_id": str(groceries.id)})
    assert _where(db, "tj3") == ("Shopping", "aggregator")  # once could be a one-off
    client.patch(f"/transactions/{_row(db, 'tj2').id}", json={"category_id": str(groceries.id)})
    db.expire_all()
    assert _where(db, "tj3") == ("Groceries", "learned")  # twice: the rest follow

    # New rows from the merchant land there too, and a rule still wins.
    _sync(db, user, *rows, _t("tj9", -40.0, "Trader Joe's", "GENERAL_MERCHANDISE_SUPERSTORES", date(2026, 8, 9)))
    assert _where(db, "tj9") == ("Groceries", "learned")


def test_a_different_pick_starts_the_count_over(client, db, user):
    _sync(db, user, *[_t(f"a{n}", -10.0, "Amazon", "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES") for n in (1, 2)])
    categories = seed_default_categories(db)
    client.patch(f"/transactions/{_row(db, 'a1').id}", json={"category_id": str(categories["electronics"].id)})
    client.patch(f"/transactions/{_row(db, 'a2').id}", json={"category_id": str(categories["clothing"].id)})
    learned = db.query(LearnedCategory).one()
    assert (learned.category_id, learned.hits) == (categories["clothing"].id, 1)


def test_a_hidden_category_sends_its_rows_to_review(client, db, user):
    _sync(db, user, _t("coffee", -5.0, "Blue Bottle", "FOOD_AND_DRINK_COFFEE"))
    coffee = seed_default_categories(db)["coffee_shops"]

    r = client.put(f"/categories/{coffee.id}/hidden", json={"hidden": True})
    assert r.status_code == 200, r.text
    assert r.json()["recategorized"] == 1
    db.expire_all()
    assert _where(db, "coffee") == ("Uncategorized", "fallback")
    food = next(c for c in client.get("/categories").json()["categories"] if c["name"] == "Food & Dining")
    assert next(c for c in food["children"] if c["name"] == "Coffee Shops")["hidden"]  # pickers leave it out

    client.put(f"/categories/{coffee.id}/hidden", json={"hidden": False})
    db.expire_all()
    assert _where(db, "coffee") == ("Coffee Shops", "aggregator")
    uncategorized = seed_default_categories(db)["uncategorized"]
    assert client.put(f"/categories/{uncategorized.id}/hidden", json={"hidden": True}).status_code == 422


def test_an_excluded_category_counts_nowhere(client, db, user):
    _sync(db, user, _t("trip", -300.0, "United", "TRAVEL_FLIGHTS"), _t("lunch", -20.0, "Chipotle", "FOOD_AND_DRINK_FAST_FOOD"))
    r = client.post("/categories", json={"name": "Work Expenses", "kind": "excluded"})
    assert r.status_code == 201, r.text
    client.patch(f"/transactions/{_row(db, 'trip').id}", json={"category_id": r.json()["id"]})

    window = mq.Window(date(2026, 8, 1), date(2026, 8, 31), "custom")
    assert mq.spend_query(db, user.id, window)["total_spent"] == 20.0
    flow = mq.cash_flow(db, user.id, window)
    assert (flow["spending"], flow["income"], flow["transfer_out"]) == (20.0, 0.0, 0.0)
    assert db.get(Category, r.json()["id"]).type == "excluded"
    # Still listed, and a spending group won't take it.
    listed = client.get("/dashboard/transactions", params={"start": "2026-08-01", "end": "2026-08-31"}).json()
    assert {t["merchant_name"] for t in listed["transactions"]} == {"United", "Chipotle"}
    spending_group = db.query(Category).filter(Category.system_key == "groceries").one().group_id
    bad = client.post("/categories", json={"name": "Reimbursable", "kind": "excluded", "group_id": str(spending_group)})
    assert bad.status_code == 422


def test_an_exact_rule_matches_the_whole_name_only(client, db, user):
    _sync(db, user, _t("shell", -50.0, "Shell", "TRANSPORTATION_GAS"), _t("shellfish", -30.0, "Shellfish Co", "FOOD_AND_DRINK_RESTAURANT"))
    groceries = seed_default_categories(db)["groceries"]
    preview = client.get(
        "/rules/preview", params={"merchant_contains": "shell", "category_id": str(groceries.id), "match_exact": True}
    )
    assert preview.json()["would_change"] == 1
    r = client.post(
        "/rules",
        json={"merchant_contains": "shell", "match_exact": True, "set_category_id": str(groceries.id), "apply_to_existing": True},
    )
    assert r.status_code == 201, r.text
    db.expire_all()
    assert _where(db, "shell") == ("Groceries", "rule")
    assert _where(db, "shellfish") == ("Restaurants & Bars", "aggregator")
