"""Disconnecting a bank and deleting an account.

Both start by telling the aggregator to drop the bank login (Plaid's
/item/remove), because that is what stops the per-Item monthly charge and
kills the access token. Plaid goes first: if it fails we keep every local row,
so the user can retry. Deleting locally first could strand a live, billed
Item that nothing in the app points at anymore. remove_item is idempotent,
so a retry after a partial failure is safe.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import (
    ChatMessage,
    Goal,
    InsightLog,
    LinkedAccount,
    NetWorthSnapshot,
    Transaction,
    User,
)
from app.integrations.bank_aggregator import BankAggregatorClient
from app.services.crypto import decrypt_token
from app.services.sync_service import refresh_net_worth

logger = logging.getLogger(__name__)


class RemovalError(Exception):
    """The aggregator refused or failed to remove a bank login; nothing local
    was deleted."""


class BankNotFound(Exception):
    pass


@dataclass
class BankLogin:
    """Every LinkedAccount row under one aggregator access token -- one bank
    login, however many accounts it covers."""

    token: str
    accounts: list[LinkedAccount]


def list_bank_logins(db: Session, user_id: UUID) -> list[BankLogin]:
    rows = (
        db.query(LinkedAccount)
        .filter(LinkedAccount.user_id == user_id)
        .order_by(LinkedAccount.institution_name, LinkedAccount.account_type, LinkedAccount.mask)
        .all()
    )
    # Grouped by decrypted token rather than item_id: item_id is null on
    # accounts linked before that column existed, the token never is.
    by_token: dict[str, list[LinkedAccount]] = {}
    for row in rows:
        by_token.setdefault(decrypt_token(row.access_token_ref), []).append(row)
    return [BankLogin(token=token, accounts=accounts) for token, accounts in by_token.items()]


def _remove_at_aggregator(logins: list[BankLogin], aggregator: BankAggregatorClient) -> None:
    failed = 0
    for login in logins:
        try:
            aggregator.remove_item(login.token)
        except Exception:
            # Never log the token. The account ids are enough to find it.
            failed += 1
            logger.exception("aggregator remove_item failed for accounts %s", [str(a.id) for a in login.accounts])
    if failed:
        raise RemovalError(f"Couldn't disconnect {failed} bank login(s) from our data provider")


def _delete_accounts(db: Session, accounts: list[LinkedAccount]) -> None:
    account_ids = [a.id for a in accounts]
    db.query(Transaction).filter(Transaction.linked_account_id.in_(account_ids)).delete(synchronize_session=False)
    db.query(LinkedAccount).filter(LinkedAccount.id.in_(account_ids)).delete(synchronize_session=False)


def disconnect_bank(db: Session, user_id: UUID, linked_account_id: UUID, aggregator: BankAggregatorClient) -> None:
    """Remove the whole bank login that `linked_account_id` belongs to,
    along with its accounts and transactions."""
    target = next(
        (
            login
            for login in list_bank_logins(db, user_id)
            if any(a.id == linked_account_id for a in login.accounts)
        ),
        None,
    )
    if target is None:
        raise BankNotFound()

    _remove_at_aggregator([target], aggregator)
    _delete_accounts(db, target.accounts)
    db.flush()

    if db.query(LinkedAccount).filter(LinkedAccount.user_id == user_id).count() == 0:
        # Nothing left to have a net worth of. Dropping the history too sends
        # the web app back to "Link your bank" instead of showing a stale
        # number from a bank the user just removed.
        db.query(NetWorthSnapshot).filter(NetWorthSnapshot.user_id == user_id).delete(synchronize_session=False)
        db.commit()
    else:
        # Older snapshots stay: they were true when recorded. Today's is
        # recomputed so the headline matches the banks that remain.
        refresh_net_worth(db, user_id)


def delete_user(db: Session, user_id: UUID, aggregator: BankAggregatorClient) -> None:
    """Erase the user and everything that hangs off them."""
    _remove_at_aggregator(list_bank_logins(db, user_id), aggregator)

    accounts = db.query(LinkedAccount).filter(LinkedAccount.user_id == user_id).all()
    if accounts:
        _delete_accounts(db, accounts)
    for model in (NetWorthSnapshot, Goal, InsightLog, ChatMessage):
        db.query(model).filter(model.user_id == user_id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()
