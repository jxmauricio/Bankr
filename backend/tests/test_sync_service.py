from app.db.models import LinkedAccount, NetWorthSnapshot, Transaction
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


def test_sync_creates_linked_accounts_and_transactions(db, user):
    result = sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())

    assert len(result.linked_accounts) == 2
    assert result.transactions_synced == 3
    assert db.query(LinkedAccount).filter(LinkedAccount.user_id == user.id).count() == 2
    assert db.query(Transaction).count() == 3


def test_sync_computes_net_worth_assets_minus_liabilities(db, user):
    # checking (asset) 2500 - credit (liability) 400 = 2100
    result = sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())

    assert result.net_worth_snapshot.total_assets == 2500.0
    assert result.net_worth_snapshot.total_liabilities == 400.0
    assert result.net_worth_snapshot.net_worth == 2100.0


def test_resync_does_not_duplicate_transactions(db, user):
    aggregator = FakeAggregatorClient()
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)

    assert db.query(Transaction).count() == 3
    assert db.query(LinkedAccount).filter(LinkedAccount.user_id == user.id).count() == 2
    # Same-day re-syncs update the existing snapshot rather than adding a
    # second point for the same date (see sync_service.py).
    assert db.query(NetWorthSnapshot).filter(NetWorthSnapshot.user_id == user.id).count() == 1


def test_expense_transactions_are_categorized(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())

    groceries = db.query(Transaction).filter(Transaction.merchant_name == "Trader Joe's").one()
    assert groceries.category.name == "Groceries"
    assert groceries.category.type == "expense"

    paycheck = db.query(Transaction).filter(Transaction.merchant_name == "Employer Inc").one()
    assert paycheck.category.name == "Income"
    assert paycheck.category.type == "income"
