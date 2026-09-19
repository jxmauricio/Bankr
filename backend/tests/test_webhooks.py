"""POST /webhooks/plaid end to end: signature gate, then dispatch by
webhook_type/code. Uses FakeAggregatorClient (a controllable bool) for
verify_webhook_signature -- the real ES256 algorithm is covered separately,
against PlaidClient itself, in test_plaid_webhook_verification.py."""

from app.api.deps import get_aggregator
from app.db.models import LinkedAccount
from app.main import app
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient

ITEM_ID = "item-abc"


def _linked(client, db, user, aggregator: FakeAggregatorClient):
    """Seed one already-linked bank (bypassing HTTP) under ITEM_ID, then
    point the app's aggregator dependency at this exact instance so the
    webhook route's own sync call shares its cursors_seen/verify toggle."""
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator, item_id=ITEM_ID)
    app.dependency_overrides[get_aggregator] = lambda: aggregator
    return client


def _post(client, payload: dict, verified_header: bool = True):
    headers = {"Plaid-Verification": "whatever-the-fake-checks"} if verified_header else {}
    return client.post("/webhooks/plaid", json=payload, headers=headers)


def test_missing_verification_header_is_rejected(client, db, user):
    aggregator = FakeAggregatorClient()
    _linked(client, db, user, aggregator)

    response = _post(client, {"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE", "item_id": ITEM_ID}, verified_header=False)

    assert response.status_code == 401
    assert len(aggregator.cursors_seen) == 1  # only the initial seed sync ran


def test_a_signature_the_aggregator_rejects_gets_401_and_no_sync(client, db, user):
    aggregator = FakeAggregatorClient(verify_webhook_result=False)
    _linked(client, db, user, aggregator)

    response = _post(client, {"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE", "item_id": ITEM_ID})

    assert response.status_code == 401
    assert len(aggregator.cursors_seen) == 1


def test_sync_updates_available_triggers_a_resync(client, db, user):
    aggregator = FakeAggregatorClient()
    _linked(client, db, user, aggregator)

    response = _post(client, {"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE", "item_id": ITEM_ID})

    assert response.status_code == 200
    assert len(aggregator.cursors_seen) == 2  # seed sync, then the webhook-triggered one


def test_transactions_removed_also_triggers_a_resync(client, db, user):
    aggregator = FakeAggregatorClient()
    _linked(client, db, user, aggregator)

    response = _post(client, {"webhook_type": "TRANSACTIONS", "webhook_code": "TRANSACTIONS_REMOVED", "item_id": ITEM_ID})

    assert response.status_code == 200
    assert len(aggregator.cursors_seen) == 2


def test_webhook_for_an_unknown_item_id_is_a_noop_not_an_error(client, db, user):
    aggregator = FakeAggregatorClient()
    _linked(client, db, user, aggregator)

    response = _post(client, {"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE", "item_id": "some-other-item"})

    assert response.status_code == 200  # Plaid shouldn't retry this forever
    assert len(aggregator.cursors_seen) == 1  # nothing here to sync


def test_webhook_with_no_item_id_is_a_noop(client, db, user):
    aggregator = FakeAggregatorClient()
    _linked(client, db, user, aggregator)

    response = _post(client, {"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE"})

    assert response.status_code == 200
    assert len(aggregator.cursors_seen) == 1


def test_item_login_required_marks_accounts_as_error(client, db, user):
    aggregator = FakeAggregatorClient()
    _linked(client, db, user, aggregator)

    response = _post(
        client,
        {
            "webhook_type": "ITEM",
            "webhook_code": "ERROR",
            "item_id": ITEM_ID,
            "error": {"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "the login is no longer valid"},
        },
    )

    assert response.status_code == 200
    statuses = {la.status for la in db.query(LinkedAccount).filter(LinkedAccount.item_id == ITEM_ID)}
    assert statuses == {"error"}
    assert len(aggregator.cursors_seen) == 1  # an errored item isn't sync-able; no resync attempted


def test_a_different_item_error_code_does_not_flip_status(client, db, user):
    aggregator = FakeAggregatorClient()
    _linked(client, db, user, aggregator)

    _post(
        client,
        {
            "webhook_type": "ITEM",
            "webhook_code": "ERROR",
            "item_id": ITEM_ID,
            "error": {"error_code": "RATE_LIMIT_EXCEEDED"},
        },
    )

    statuses = {la.status for la in db.query(LinkedAccount).filter(LinkedAccount.item_id == ITEM_ID)}
    assert statuses == {"active"}


def test_login_repaired_reactivates_and_resyncs(client, db, user):
    aggregator = FakeAggregatorClient()
    _linked(client, db, user, aggregator)
    for la in db.query(LinkedAccount).filter(LinkedAccount.item_id == ITEM_ID):
        la.status = "error"
    db.commit()

    response = _post(client, {"webhook_type": "ITEM", "webhook_code": "LOGIN_REPAIRED", "item_id": ITEM_ID})

    assert response.status_code == 200
    statuses = {la.status for la in db.query(LinkedAccount).filter(LinkedAccount.item_id == ITEM_ID)}
    assert statuses == {"active"}
    assert len(aggregator.cursors_seen) == 2  # reactivating also re-syncs


def test_an_unrecognized_webhook_code_is_ignored_not_errored(client, db, user):
    aggregator = FakeAggregatorClient()
    _linked(client, db, user, aggregator)

    response = _post(client, {"webhook_type": "ITEM", "webhook_code": "SOMETHING_FUTURE_VERSIONS_ADD", "item_id": ITEM_ID})

    assert response.status_code == 200
    assert len(aggregator.cursors_seen) == 1
