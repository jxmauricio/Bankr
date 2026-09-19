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


def _txn(txn_id, amount, *, pending=False, pending_id=None, account="acc_checking"):
    from datetime import date

    from app.integrations.bank_aggregator import AggregatorTransaction

    return AggregatorTransaction(
        aggregator_transaction_id=txn_id,
        aggregator_account_id=account,
        amount=amount,
        date=date(2026, 9, 10),
        merchant_name="Shell",
        raw_category="TRANSPORTATION_GAS",
        is_pending=pending,
        pending_transaction_id=pending_id,
    )


def test_removed_transactions_are_deleted(db, user):
    aggregator = FakeAggregatorClient(transactions_by_account={"acc_checking": [_txn("t_pending", -40.0, pending=True)]})
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)
    assert db.query(Transaction).count() == 1

    aggregator.transactions_by_account = {"acc_checking": []}
    aggregator.removed_ids = ["t_pending"]
    result = sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)

    assert result.transactions_removed == 1
    assert db.query(Transaction).count() == 0


def test_pending_charge_that_posts_is_not_double_counted(db, user):
    # Posting issues a new id; even without an explicit removal, the posted
    # row's pending_transaction_id retires the stale pending row.
    aggregator = FakeAggregatorClient(transactions_by_account={"acc_checking": [_txn("t_pending", -40.0, pending=True)]})
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)

    aggregator.transactions_by_account = {"acc_checking": [_txn("t_posted", -42.5, pending_id="t_pending")]}
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)

    rows = db.query(Transaction).all()
    assert [(r.aggregator_transaction_id, float(r.amount), r.is_pending) for r in rows] == [("t_posted", -42.5, False)]


def test_sync_cursor_is_persisted_and_passed_back(db, user):
    aggregator = FakeAggregatorClient()
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)

    assert aggregator.cursors_seen == [None, "cursor-1"]
    cursors = {la.sync_cursor for la in db.query(LinkedAccount).filter(LinkedAccount.user_id == user.id)}
    assert cursors == {"cursor-2"}


def test_linking_a_second_bank_keeps_the_first_banks_balances_in_net_worth(db, user):
    from app.integrations.bank_aggregator import AggregatorAccount

    sync_user_accounts(db, user.id, "token-bank-a", aggregator=FakeAggregatorClient())  # 2500 - 400
    second_bank = FakeAggregatorClient(
        accounts=[
            AggregatorAccount(
                aggregator_account_id="acc_other_savings",
                institution_name="Other Bank",
                account_type="savings",
                current_balance=1000.0,
                available_balance=1000.0,
            )
        ],
        transactions_by_account={},
    )
    result = sync_user_accounts(db, user.id, "token-bank-b", aggregator=second_bank)

    assert float(result.net_worth_snapshot.net_worth) == 3100.0


def test_account_balances_are_stored_per_account(db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    balances = {
        la.aggregator_account_id: float(la.current_balance)
        for la in db.query(LinkedAccount).filter(LinkedAccount.user_id == user.id)
    }
    assert balances == {"acc_checking": 2500.0, "acc_credit": 400.0}


def test_fresh_link_backfills_item_id_via_the_aggregator(db, user):
    aggregator = FakeAggregatorClient()
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)

    assert aggregator.get_item_id_calls == ["fake-token"]  # fetched exactly once
    item_ids = {la.item_id for la in db.query(LinkedAccount).filter(LinkedAccount.user_id == user.id)}
    assert item_ids == {"item-fake-token"}


def test_a_known_item_id_is_reused_without_calling_the_aggregator_again(db, user):
    aggregator = FakeAggregatorClient()
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)

    assert aggregator.get_item_id_calls == ["fake-token"]  # not called again on resync


def test_a_webhook_supplied_item_id_is_stored_and_then_reused(db, user):
    aggregator = FakeAggregatorClient()
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator, item_id="item-from-webhook")
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)  # e.g. the Refresh button

    assert aggregator.get_item_id_calls == []  # never needed a backfill
    item_ids = {la.item_id for la in db.query(LinkedAccount).filter(LinkedAccount.user_id == user.id)}
    assert item_ids == {"item-from-webhook"}
