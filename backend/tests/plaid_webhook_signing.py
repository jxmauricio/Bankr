"""A real EC keypair standing in for Plaid's own webhook signing key, so
tests exercise the actual ES256 verify path (app/integrations/plaid_client.py
PlaidClient.verify_webhook_signature) rather than mocking it away."""

import base64
import hashlib
import json
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jws

KEY_ID = "test-signing-key"


def _b64url_uint(n: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()


class FakeWebhookSigner:
    """One EC keypair, reused across a test. `public_jwk` is what a stubbed
    webhook_verification_key_get would hand back; `sign` produces the
    Plaid-Verification header value for a given raw body."""

    def __init__(self, key_id: str = KEY_ID):
        self.key_id = key_id
        self._private_key = ec.generate_private_key(ec.SECP256R1())
        numbers = self._private_key.public_key().public_numbers()
        self.public_jwk = {
            "kty": "EC",
            "crv": "P-256",
            "kid": key_id,
            "x": _b64url_uint(numbers.x),
            "y": _b64url_uint(numbers.y),
            "alg": "ES256",
            "use": "sig",
        }

    def _pem(self) -> bytes:
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def sign(self, raw_body: bytes, *, iat: float | None = None, body_hash: str | None = None) -> str:
        """`iat`/`body_hash` overrides let a test forge a stale timestamp or
        a mismatched hash while keeping the signature itself genuinely valid
        -- the interesting failure cases are a *validly signed* bad claim,
        not a broken signature."""
        payload = json.dumps(
            {
                "iat": int(iat if iat is not None else time.time()),
                "request_body_sha256": body_hash if body_hash is not None else hashlib.sha256(raw_body).hexdigest(),
            }
        ).encode()
        return jws.sign(payload, self._pem(), algorithm="ES256", headers={"kid": self.key_id})
