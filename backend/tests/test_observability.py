"""What Sentry would actually receive. A capturing transport stands in for
the network, so these assert on the real event payload -- the point is that
bank data, chat text and credentials never leave the app."""

import json

import pytest
import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from app.config import Settings
from app.observability import init_sentry, scrub_event

_DSN = "https://publickey@o0.ingest.sentry.io/1"


class _Capture(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.events: list[dict] = []

    def capture_envelope(self, envelope):
        event = envelope.get_event()
        if event is not None:
            self.events.append(event)


def _settings(dsn: str) -> Settings:
    return Settings(
        database_url="postgresql://x", session_jwt_secret="s", token_encryption_key="k", sentry_dsn=dsn
    )


@pytest.fixture
def capture():
    transport = _Capture()
    yield transport
    sentry_sdk.get_global_scope().set_client(None)


def test_disabled_without_a_dsn():
    assert init_sentry(_settings("")) is False


def _secret(*parts: str) -> str:
    # Assembled at runtime: Sentry attaches source lines around each frame,
    # and the in-process TestClient puts this file in the stack, so a literal
    # here would "leak" from the test's own source rather than from real data.
    return "".join(parts)


def test_unhandled_error_reports_a_stack_trace_but_no_request_or_local_data(capture):
    assert init_sentry(_settings(_DSN), transport=capture) is True
    app = FastAPI()  # built after init so the integrations instrument it

    @app.post("/boom")
    async def boom(request: Request):
        await request.json()
        checking_balance = f"{balance}"  # a local an exception frame would normally carry
        raise RuntimeError(f"failed ({len(checking_balance)})")

    balance = f"{48000 + 213}.55"
    chat_text = _secret("how much did I spend at ", "Planned ", "Parenthood")
    password = _secret("hunter2", "-secret")
    session = _secret("session-", "jwt-value")
    response = TestClient(app, raise_server_exceptions=False).post(
        "/boom",
        json={"message": chat_text, "password": password},
        headers={"Authorization": f"Bearer {session}"},
    )
    sentry_sdk.flush()

    assert response.status_code == 500
    assert len(capture.events) == 1
    payload = json.dumps(capture.events[0])
    assert "RuntimeError" in payload
    for secret in (chat_text, password, session, balance):
        assert secret not in payload, "request or local data leaked into the Sentry event"
    request_context = capture.events[0]["request"]
    assert not request_context.get("data")  # body dropped, not just scrubbed
    assert request_context["headers"]["authorization"] == "[Filtered]"


def test_sqlalchemy_bound_parameters_are_scrubbed_from_exception_text():
    event = {
        "exception": {
            "values": [
                {
                    "value": (
                        "(psycopg2.errors.UniqueViolation) duplicate key\n"
                        "[SQL: INSERT INTO users (email) VALUES (%(email)s)]\n"
                        "[parameters: {'email': 'friend@example.com'}]\n"
                        "(Background on this error at: https://sqlalche.me/e/20/gkpj)"
                    )
                }
            ]
        }
    }

    value = scrub_event(event, {})["exception"]["values"][0]["value"]

    assert "friend@example.com" not in value
    assert "[parameters: <scrubbed>]" in value
    assert "duplicate key" in value and "Background on this error" in value
