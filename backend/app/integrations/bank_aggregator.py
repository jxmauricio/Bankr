"""Adapter interface for bank data aggregators.

Bankr runs on Plaid (see plaid_client.py) but every call site in the app
depends on this Protocol, not on Plaid directly, so swapping aggregators is a
matter of writing one new adapter rather than a rewrite -- which is exactly
what happened once already: this app originally ran on Teller, which shut
down its API in July 2026.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass
class AggregatorAccount:
    aggregator_account_id: str
    institution_name: str
    account_type: str  # checking | savings | credit | loan | investment
    current_balance: float
    available_balance: float | None


@dataclass
class AggregatorTransaction:
    aggregator_transaction_id: str
    aggregator_account_id: str
    amount: float
    date: date
    merchant_name: str | None
    raw_category: str | None
    is_pending: bool


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

    def list_transactions(
        self, access_token: str, aggregator_account_id: str, since: date | None = None
    ) -> list[AggregatorTransaction]:
        """Return transactions for a single account, optionally since a given date."""
        ...

    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        """Verify an inbound webhook actually came from the aggregator."""
        ...
