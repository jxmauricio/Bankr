"""Adapter interface for bank data aggregators.

Bankr runs on Plaid (see plaid_client.py) but every call site in the app
depends on this Protocol, not on Plaid directly, so swapping aggregators is a
matter of writing one new adapter rather than a rewrite -- which is exactly
what happened once already: this app originally ran on Teller, which shut
down its API in July 2026.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass
class AggregatorAccount:
    aggregator_account_id: str
    institution_name: str
    account_type: str  # checking | savings | credit | loan | investment
    current_balance: float
    available_balance: float | None
    name: str | None = None
    mask: str | None = None  # last 4 digits, shown so the user can recognize the account


@dataclass
class AggregatorTransaction:
    aggregator_transaction_id: str
    aggregator_account_id: str
    amount: float
    date: date
    merchant_name: str | None
    raw_category: str | None
    is_pending: bool
    # Set on a posted transaction that replaced a pending one (the aggregator
    # issues a new id when a charge posts) -- lets sync drop the stale
    # pending row even if the aggregator's own "removed" signal is missed.
    pending_transaction_id: str | None = None


@dataclass
class TransactionSyncResult:
    """One fully-paginated incremental sync: everything since `cursor`.

    `removed_ids` matters for correctness, not just tidiness -- a pending
    charge that later posts comes back as a *new* id plus a removal of the
    old one; missing the removal double-counts the charge."""

    added: list[AggregatorTransaction] = field(default_factory=list)
    modified: list[AggregatorTransaction] = field(default_factory=list)
    removed_ids: list[str] = field(default_factory=list)
    next_cursor: str | None = None


class BankAggregatorClient(Protocol):
    def create_link_token(self, user_id: str) -> str:
        """Return a short-lived token the client SDK uses to launch the
        aggregator's hosted bank-linking UI."""
        ...

    def exchange_public_token(self, public_token: str) -> str:
        """Exchange the client SDK's public token for a durable access token
        the backend stores and uses for all subsequent aggregator calls."""
        ...

    def list_accounts(self, access_token: str) -> list[AggregatorAccount]:
        """Return all accounts the user granted access to under this enrollment."""
        ...

    def sync_transactions(self, access_token: str, cursor: str | None) -> TransactionSyncResult:
        """Return every transaction change across all of this enrollment's
        accounts since `cursor` (None = full history), fully paginated."""
        ...

    def get_item_id(self, access_token: str) -> str:
        """Return the stable id for this whole bank login (every account
        under one access token shares one). An inbound webhook only ever
        carries this id, never the access token itself, so it's how
        app/services/webhook_service.py finds the right LinkedAccount rows."""
        ...

    def update_item_webhook(self, access_token: str, webhook_url: str) -> None:
        """Attach (or change) the webhook URL for an already-linked Item.
        create_link_token only sets one for *new* links, so this is what
        brings an existing one up to date -- see
        app/services/webhook_backfill.py."""
        ...

    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        """Verify an inbound webhook body actually came from the aggregator,
        given its raw bytes and the aggregator's verification header."""
        ...
