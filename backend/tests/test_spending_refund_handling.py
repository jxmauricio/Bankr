"""Regression test for a bug found via live Plaid sandbox data: a refund
(positive amount) tagged under an expense category could net a category
positive and get reported as spending via abs(), or show up inside the
"Spending" itemized list itself. See app/services/money_query.py spend_query.

Refunds now net against spending in their own top-level category (like a
card statement), floored at zero -- so the $500 United refund offsets
Travel, never the $50 Uber ride under Transportation."""

from datetime import date, datetime, timezone

import pytest

from app.integrations.bank_aggregator import AggregatorAccount, AggregatorTransaction
from app.services import money_query as mq
from app.services.dashboard_service import get_itemized_transactions
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))


def _aggregator_with_refund() -> FakeAggregatorClient:
    accounts = [
        AggregatorAccount(
            aggregator_account_id="acc_checking",
            institution_name="Fake Bank",
            account_type="checking",
            current_balance=1000.0,
            available_balance=1000.0,
        )
    ]
    transactions = {
        "acc_checking": [
            AggregatorTransaction(
                aggregator_transaction_id="txn_flight",
                aggregator_account_id="acc_checking",
                amount=-50.0,  # a small Uber ride to the airport
                date=date(2026, 8, 1),
                merchant_name="Uber",
                raw_category="transportation_taxis_and_ride_shares",
                is_pending=False,
            ),
            AggregatorTransaction(
                aggregator_transaction_id="txn_refund",
                aggregator_account_id="acc_checking",
                amount=500.0,  # a much bigger airline refund, same category bucket
                date=date(2026, 8, 2),
                merchant_name="United Airlines",
                raw_category="travel_flights",
                is_pending=False,
            ),
        ]
    }
    return FakeAggregatorClient(accounts=accounts, transactions_by_account=transactions)


def test_refund_does_not_get_reported_as_spending(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=_aggregator_with_refund())

    spending = mq.spend_query(db, user.id, mq.resolve_window(date(2026, 8, 20), "this_month"), group_by="category")
    # Only the $50 Uber ride counts as spending -- the $500 refund must not
    # flip the total into a bogus "-$450 spent", and it's surfaced, not hidden.
    assert spending["total_spent"] == 50.0
    assert [(g["name"], g["amount"]) for g in spending["groups"]] == [("Transportation", 50.0)]
    assert spending["refunds_exceeding_spend"] == 500.0


def test_itemized_spending_list_shows_the_refund_but_headline_stays_floored(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=_aggregator_with_refund())

    spending = get_itemized_transactions(db, user.id, kind="expense", period="month")
    assert spending["total"] == 50.0
    assert {i["merchant_name"] for i in spending["items"]} == {"Uber", "United Airlines"}
