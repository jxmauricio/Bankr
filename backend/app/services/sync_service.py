"""Pulls fresh accounts + transactions from the aggregator and updates
Postgres: LinkedAccount rows, categorized Transaction rows, and a fresh
NetWorthSnapshot.

Takes a BankAggregatorClient (see app/integrations/bank_aggregator.py) as a
parameter rather than importing PlaidClient directly, so tests can inject a
fake adapter instead of hitting Plaid's API (see tests/).
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import LinkedAccount, NetWorthSnapshot, Transaction
from app.db.seed_categories import seed_default_categories
from app.integrations.bank_aggregator import AggregatorTransaction, BankAggregatorClient
from app.services.category_mapper import map_raw_category
from app.services.crypto import encrypt_token
from app.services.goal_service import recompute_goal_progress

LIABILITY_ACCOUNT_TYPES = {"credit", "loan"}


@dataclass
class SyncResult:
    linked_accounts: list[LinkedAccount]
    net_worth_snapshot: NetWorthSnapshot
    transactions_synced: int
    transactions_removed: int = 0


def sync_user_accounts(
    db: Session,
    user_id: UUID,
    access_token: str,
    aggregator: BankAggregatorClient,
    item_id: str | None = None,
) -> SyncResult:
    """`item_id` is Plaid's id for this whole bank login, used to route
    webhooks back to these rows (see app/services/webhook_service.py).
    Pass it when it's already known (fresh link, or a webhook that already
    named it); otherwise it's read off an existing row for this login, or
    fetched once via aggregator.get_item_id and backfilled -- so accounts
    linked before this column existed pick one up on their next sync."""
    categories = seed_default_categories(db)

    aggregator_accounts = aggregator.list_accounts(access_token)
    encrypted_token = encrypt_token(access_token)
    now = datetime.now(timezone.utc)

    linked_by_aggregator_id: dict[str, LinkedAccount] = {}
    for acc in aggregator_accounts:
        linked = (
            db.query(LinkedAccount)
            .filter(
                LinkedAccount.user_id == user_id,
                LinkedAccount.aggregator_account_id == acc.aggregator_account_id,
            )
            .one_or_none()
        )
        if linked is None:
            linked = LinkedAccount(
                user_id=user_id,
                aggregator="plaid",
                aggregator_account_id=acc.aggregator_account_id,
            )
            db.add(linked)

        linked.institution_name = acc.institution_name
        linked.name = acc.name
        linked.mask = acc.mask
        linked.account_type = acc.account_type
        linked.current_balance = acc.current_balance
        linked.balance_as_of = now
        linked.access_token_ref = encrypted_token
        linked.last_synced_at = now
        linked.status = "active"
        linked_by_aggregator_id[acc.aggregator_account_id] = linked
    db.flush()
    linked_accounts = list(linked_by_aggregator_id.values())

    # One cursor per bank login, shared by all its accounts -- any of them
    # holds the current value. A brand-new login has none: full history.
    cursor = next((la.sync_cursor for la in linked_accounts if la.sync_cursor), None)
    changes = aggregator.sync_transactions(access_token, cursor)

    transactions_synced = 0
    for txn in [*changes.added, *changes.modified]:
        linked = linked_by_aggregator_id.get(txn.aggregator_account_id)
        if linked is None:
            continue  # an account the user didn't grant access to
        _upsert_transaction(db, txn, linked.id, linked.account_type, categories)
        transactions_synced += 1

    # Deleting pending rows that were replaced by their posted version is
    # what prevents double-counting a charge. Plaid reports these in
    # `removed`; pending_transaction_id is a belt-and-braces second signal.
    stale_ids = set(changes.removed_ids)
    stale_ids.update(
        t.pending_transaction_id for t in [*changes.added, *changes.modified] if t.pending_transaction_id
    )
    transactions_removed = 0
    if stale_ids:
        transactions_removed = (
            db.query(Transaction)
            .filter(
                Transaction.aggregator_transaction_id.in_(stale_ids),
                Transaction.linked_account_id.in_([la.id for la in linked_accounts]),
            )
            .delete(synchronize_session=False)
        )

    resolved_item_id = item_id or next((la.item_id for la in linked_accounts if la.item_id), None)
    if resolved_item_id is None:
        resolved_item_id = aggregator.get_item_id(access_token)

    for linked in linked_accounts:
        linked.sync_cursor = changes.next_cursor
        linked.item_id = resolved_item_id

    total_assets, total_liabilities = _balance_totals(db, user_id)

    # Upsert on (user_id, date) rather than always inserting: a trend chart
    # wants one point per day, and "today's" snapshot should always reflect
    # the most recent sync if the user re-syncs multiple times in a day.
    today = date.today()
    snapshot = (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.user_id == user_id, NetWorthSnapshot.date == today)
        .one_or_none()
    )
    if snapshot is None:
        snapshot = NetWorthSnapshot(user_id=user_id, date=today)
        db.add(snapshot)

    snapshot.total_assets = total_assets
    snapshot.total_liabilities = total_liabilities
    snapshot.net_worth = total_assets - total_liabilities
    db.flush()

    recompute_goal_progress(db, user_id, snapshot)
    db.commit()

    return SyncResult(
        linked_accounts=linked_accounts,
        net_worth_snapshot=snapshot,
        transactions_synced=transactions_synced,
        transactions_removed=transactions_removed,
    )


def _upsert_transaction(
    db: Session, txn: AggregatorTransaction, linked_account_id: UUID, account_type: str, categories: dict
) -> None:
    existing = (
        db.query(Transaction)
        .filter(Transaction.aggregator_transaction_id == txn.aggregator_transaction_id)
        .one_or_none()
    )
    if existing is None:
        existing = Transaction(aggregator_transaction_id=txn.aggregator_transaction_id)
        db.add(existing)

    category = categories[map_raw_category(txn.raw_category, txn.amount, account_type)]
    existing.linked_account_id = linked_account_id
    existing.amount = txn.amount
    existing.date = txn.date
    existing.merchant_name = txn.merchant_name
    existing.raw_aggregator_category = txn.raw_category
    existing.bankr_category_id = category.id
    existing.is_pending = txn.is_pending
    existing.pending_transaction_id = txn.pending_transaction_id


def _balance_totals(db: Session, user_id: UUID) -> tuple[float, float]:
    """Assets and liabilities across *all* of the user's active accounts,
    not just the bank login being synced -- otherwise linking a second bank
    would overwrite net worth with only that bank's balances."""
    total_assets = 0.0
    total_liabilities = 0.0
    accounts = (
        db.query(LinkedAccount)
        .filter(LinkedAccount.user_id == user_id, LinkedAccount.status == "active")
        .all()
    )
    for account in accounts:
        balance = float(account.current_balance or 0)
        if account.account_type in LIABILITY_ACCOUNT_TYPES:
            total_liabilities += balance
        else:
            total_assets += balance
    return total_assets, total_liabilities
