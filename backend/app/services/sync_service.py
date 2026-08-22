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
from app.integrations.bank_aggregator import BankAggregatorClient
from app.services.category_mapper import map_raw_category
from app.services.crypto import encrypt_token
from app.services.goal_service import recompute_goal_progress

LIABILITY_ACCOUNT_TYPES = {"credit", "loan"}


@dataclass
class SyncResult:
    linked_accounts: list[LinkedAccount]
    net_worth_snapshot: NetWorthSnapshot
    transactions_synced: int


def sync_user_accounts(
    db: Session, user_id: UUID, access_token: str, aggregator: BankAggregatorClient
) -> SyncResult:
    categories = seed_default_categories(db)

    aggregator_accounts = aggregator.list_accounts(access_token)
    encrypted_token = encrypt_token(access_token)

    total_assets = 0.0
    total_liabilities = 0.0
    linked_accounts: list[LinkedAccount] = []
    transactions_synced = 0

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
        linked.account_type = acc.account_type
        linked.access_token_ref = encrypted_token
        linked.last_synced_at = datetime.now(timezone.utc)
        linked.status = "active"
        db.flush()
        linked_accounts.append(linked)

        if acc.account_type in LIABILITY_ACCOUNT_TYPES:
            total_liabilities += acc.current_balance
        else:
            total_assets += acc.current_balance

        for txn in aggregator.list_transactions(access_token, acc.aggregator_account_id):
            existing = (
                db.query(Transaction)
                .filter(Transaction.aggregator_transaction_id == txn.aggregator_transaction_id)
                .one_or_none()
            )
            category_name = map_raw_category(txn.raw_category, txn.amount)
            category = categories[category_name]

            if existing is None:
                existing = Transaction(aggregator_transaction_id=txn.aggregator_transaction_id)
                db.add(existing)

            existing.linked_account_id = linked.id
            existing.amount = txn.amount
            existing.date = txn.date
            existing.merchant_name = txn.merchant_name
            existing.raw_aggregator_category = txn.raw_category
            existing.bankr_category_id = category.id
            existing.is_pending = txn.is_pending
            transactions_synced += 1

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
    )
