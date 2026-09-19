"""attach_webhook_to_existing_items backfills a webhook URL onto Items that
predate PLAID_WEBHOOK_URL (or a changed one, e.g. a new ngrok tunnel)."""

from app.integrations.bank_aggregator import AggregatorAccount
from app.services.sync_service import sync_user_accounts
from app.services.webhook_backfill import attach_webhook_to_existing_items
from tests.fake_aggregator import FakeAggregatorClient


def test_backfill_updates_every_distinct_item_exactly_once(db, user):
    aggregator = FakeAggregatorClient()
    sync_user_accounts(db, user.id, "token-a", aggregator=aggregator)  # 2 accounts, 1 item
    sync_user_accounts(
        db,
        user.id,
        "token-b",
        aggregator=FakeAggregatorClient(
            accounts=[AggregatorAccount("acc_other", "Other Bank", "savings", 500.0, 500.0)],
            transactions_by_account={},
        ),
    )

    updated = attach_webhook_to_existing_items(db, aggregator, "https://example.ngrok-free.dev/webhooks/plaid")

    assert updated == 2
    # A set internally -- order isn't meaningful, just that each distinct
    # Item got updated exactly once.
    assert sorted(aggregator.updated_webhooks) == [
        ("token-a", "https://example.ngrok-free.dev/webhooks/plaid"),
        ("token-b", "https://example.ngrok-free.dev/webhooks/plaid"),
    ]


def test_backfill_is_a_noop_with_no_linked_accounts(db, user):
    aggregator = FakeAggregatorClient()
    assert attach_webhook_to_existing_items(db, aggregator, "https://example.ngrok-free.dev/webhooks/plaid") == 0
    assert aggregator.updated_webhooks == []
