"""Regression test for a bug found via live Plaid sandbox data: a refund
(positive amount) tagged under an expense category could net a category
positive and get reported as spending via abs(), or show up inside the
"Spending" itemized list itself. See app/agent/tools.py get_spending_by_category
and app/services/dashboard_service.py get_itemized_transactions."""

from datetime import date

from app.agent.tools import get_spending_by_category
from app.integrations.bank_aggregator import AggregatorAccount, AggregatorTransaction
from app.services.dashboard_service import get_itemized_transactions
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


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

    spending = get_spending_by_category(db, user.id, period="month")
    # Only the $50 Uber ride counts as spending -- the $500 refund must not
    # net against it and flip the sign into a bogus "$450 spent" figure.
    assert spending["by_category"]["Transportation"] == 50.0


def test_refund_does_not_appear_in_itemized_spending_list(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=_aggregator_with_refund())

    spending = get_itemized_transactions(db, user.id, kind="expense", period="month")
    assert spending["total"] == 50.0
    assert len(spending["items"]) == 1
    assert spending["items"][0]["merchant_name"] == "Uber"
