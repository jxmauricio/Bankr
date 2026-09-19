from datetime import date

from app.integrations.bank_aggregator import (
    AggregatorAccount,
    AggregatorTransaction,
    TransactionSyncResult,
)


class FakeAggregatorClient:
    """Canned BankAggregatorClient for tests -- never touches Plaid's API."""

    def __init__(
        self,
        accounts: list[AggregatorAccount] | None = None,
        transactions_by_account: dict[str, list[AggregatorTransaction]] | None = None,
        removed_ids: list[str] | None = None,
        item_id: str | None = None,
        verify_webhook_result: bool = True,
    ):
        self.accounts = accounts if accounts is not None else self._default_accounts()
        self.transactions_by_account = (
            transactions_by_account if transactions_by_account is not None else self._default_transactions()
        )
        self.removed_ids = removed_ids or []
        self.cursors_seen: list[str | None] = []
        self.item_id = item_id
        self.get_item_id_calls: list[str] = []
        self.verify_webhook_result = verify_webhook_result
        self.updated_webhooks: list[tuple[str, str]] = []

    @staticmethod
    def _default_accounts() -> list[AggregatorAccount]:
        return [
            AggregatorAccount(
                aggregator_account_id="acc_checking",
                institution_name="Fake Bank",
                account_type="checking",
                current_balance=2500.0,
                available_balance=2500.0,
            ),
            AggregatorAccount(
                aggregator_account_id="acc_credit",
                institution_name="Fake Bank",
                account_type="credit",
                current_balance=400.0,
                available_balance=1600.0,
            ),
        ]

    @staticmethod
    def _default_transactions() -> dict[str, list[AggregatorTransaction]]:
        return {
            "acc_checking": [
                AggregatorTransaction(
                    aggregator_transaction_id="txn_paycheck",
                    aggregator_account_id="acc_checking",
                    amount=3000.0,
                    date=date(2026, 8, 1),
                    merchant_name="Employer Inc",
                    raw_category="income_wages",
                    is_pending=False,
                ),
                AggregatorTransaction(
                    aggregator_transaction_id="txn_groceries",
                    aggregator_account_id="acc_checking",
                    amount=-120.50,
                    date=date(2026, 8, 3),
                    merchant_name="Trader Joe's",
                    raw_category="food_and_drink_groceries",
                    is_pending=False,
                ),
            ],
            "acc_credit": [
                AggregatorTransaction(
                    aggregator_transaction_id="txn_dining",
                    aggregator_account_id="acc_credit",
                    amount=-45.00,
                    date=date(2026, 8, 5),
                    merchant_name="Ramen Spot",
                    raw_category="food_and_drink_restaurant",
                    is_pending=False,
                ),
            ],
        }

    def create_link_token(self, user_id: str) -> str:
        return f"link-sandbox-{user_id}"

    def exchange_public_token(self, public_token: str) -> str:
        return f"access-{public_token}"

    def list_accounts(self, access_token: str) -> list[AggregatorAccount]:
        return self.accounts

    def sync_transactions(self, access_token: str, cursor: str | None) -> TransactionSyncResult:
        """Always returns the full canned set as `added` -- sync upserts, so
        repeating it is harmless -- and advances the cursor each call so
        tests can assert it was persisted and passed back."""
        self.cursors_seen.append(cursor)
        return TransactionSyncResult(
            added=[t for txns in self.transactions_by_account.values() for t in txns],
            removed_ids=list(self.removed_ids),
            next_cursor=f"cursor-{len(self.cursors_seen)}",
        )

    def get_item_id(self, access_token: str) -> str:
        """Deterministic from the access token by default, so tests that
        never care about item_id still get stable, distinguishable values;
        set `item_id=` explicitly to control it."""
        self.get_item_id_calls.append(access_token)
        return self.item_id or f"item-{access_token}"

    def update_item_webhook(self, access_token: str, webhook_url: str) -> None:
        self.updated_webhooks.append((access_token, webhook_url))

    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        return self.verify_webhook_result
