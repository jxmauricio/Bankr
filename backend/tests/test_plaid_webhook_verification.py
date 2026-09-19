"""PlaidClient.verify_webhook_signature against a real ES256 keypair and a
stubbed webhook_verification_key_get -- the exact algorithm from
plaid.com/docs/api/webhooks/webhook-verification: verify the JWT's
signature, reject a stale iat (>5 min), and check request_body_sha256
against the raw body in constant time."""

import json
from types import SimpleNamespace

import plaid
import pytest

from app.integrations import plaid_client
from tests.plaid_webhook_signing import FakeWebhookSigner


class _StubApi:
    def __init__(self, jwk: dict, *, fails: bool = False):
        self.jwk = jwk
        self.fails = fails
        self.calls = 0

    def webhook_verification_key_get(self, request):
        self.calls += 1
        if self.fails:
            raise plaid.ApiException(status=400, reason="Bad Request")
        return SimpleNamespace(key=SimpleNamespace(**self.jwk, expired_at=None))


@pytest.fixture(autouse=True)
def _clear_key_cache():
    plaid_client._webhook_key_cache.clear()
    yield
    plaid_client._webhook_key_cache.clear()


@pytest.fixture
def signer():
    return FakeWebhookSigner()


def test_a_correctly_signed_webhook_verifies(monkeypatch, signer):
    api = _StubApi(signer.public_jwk)
    monkeypatch.setattr(plaid_client, "_client", lambda: api)
    body = json.dumps({"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE"}).encode()

    assert plaid_client.PlaidClient().verify_webhook_signature(body, signer.sign(body)) is True
    assert api.calls == 1


def test_the_verification_key_is_cached_across_calls(monkeypatch, signer):
    api = _StubApi(signer.public_jwk)
    monkeypatch.setattr(plaid_client, "_client", lambda: api)
    body = b'{"a": 1}'

    client = plaid_client.PlaidClient()
    assert client.verify_webhook_signature(body, signer.sign(body)) is True
    assert client.verify_webhook_signature(body, signer.sign(body)) is True
    assert api.calls == 1  # second call reused the cached key


def test_a_tampered_body_fails_even_with_a_validly_signed_header(monkeypatch, signer):
    api = _StubApi(signer.public_jwk)
    monkeypatch.setattr(plaid_client, "_client", lambda: api)
    original_body = b'{"item_id": "real-item"}'
    header = signer.sign(original_body)

    tampered_body = b'{"item_id": "someone-elses-item"}'
    assert plaid_client.PlaidClient().verify_webhook_signature(tampered_body, header) is False


def test_a_signature_from_a_different_key_fails(monkeypatch, signer):
    wrong_signer = FakeWebhookSigner(key_id=signer.key_id)  # same kid, different keypair
    api = _StubApi(signer.public_jwk)  # server only knows the *real* signer's key
    monkeypatch.setattr(plaid_client, "_client", lambda: api)
    body = b'{"a": 1}'

    assert plaid_client.PlaidClient().verify_webhook_signature(body, wrong_signer.sign(body)) is False


def test_a_stale_webhook_is_rejected(monkeypatch, signer):
    api = _StubApi(signer.public_jwk)
    monkeypatch.setattr(plaid_client, "_client", lambda: api)
    body = b'{"a": 1}'
    ten_minutes_ago = plaid_client.time.time() - 600

    header = signer.sign(body, iat=ten_minutes_ago)
    assert plaid_client.PlaidClient().verify_webhook_signature(body, header) is False


def test_unknown_kid_is_rejected_without_raising(monkeypatch, signer):
    api = _StubApi(signer.public_jwk, fails=True)
    monkeypatch.setattr(plaid_client, "_client", lambda: api)
    body = b'{"a": 1}'

    assert plaid_client.PlaidClient().verify_webhook_signature(body, signer.sign(body)) is False


def test_garbage_header_is_rejected_without_raising():
    assert plaid_client.PlaidClient().verify_webhook_signature(b"{}", "not-a-jwt") is False


def test_wrong_algorithm_in_header_is_rejected(monkeypatch, signer):
    api = _StubApi(signer.public_jwk)
    monkeypatch.setattr(plaid_client, "_client", lambda: api)
    # A validly-formed HS256 token (a different algorithm than Plaid ever
    # actually uses) must be rejected on the alg check, before any key fetch.
    from jose import jws

    body = b'{"a": 1}'
    forged = jws.sign(b'{"iat": 0, "request_body_sha256": "x"}', "any-secret", algorithm="HS256")
    assert plaid_client.PlaidClient().verify_webhook_signature(body, forged) is False
    assert api.calls == 0
