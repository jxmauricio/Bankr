"""Error monitoring (Sentry).

This app handles bank balances, transactions and private chat, so the
defaults are inverted: Sentry gets stack traces and nothing else. What that
means in practice:

- No request bodies (chat messages, passwords, public tokens) -- the
  FastAPI integration attaches them unless told not to.
- No local variables in stack frames (they'd hold transactions, balances,
  message text, access tokens).
- No user IP / email (send_default_pii stays False).
- No performance tracing; it isn't needed to find bugs and adds request
  metadata.
- Exception messages are scrubbed of SQLAlchemy's "[parameters: ...]"
  suffix, which echoes the bound values of the failing statement.

Initialisation is a no-op without SENTRY_DSN.
"""

import re

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.config import Settings

_SQL_PARAMETERS = re.compile(r"\[parameters: .*?\](?=\n|$)", re.DOTALL)


def scrub_event(event: dict, hint: dict) -> dict | None:
    for exception in event.get("exception", {}).get("values", []):
        if exception.get("value"):
            exception["value"] = _SQL_PARAMETERS.sub("[parameters: <scrubbed>]", exception["value"])
    message = event.get("logentry", {}).get("message") or event.get("message")
    if message:
        scrubbed = _SQL_PARAMETERS.sub("[parameters: <scrubbed>]", message)
        if "logentry" in event:
            event["logentry"]["message"] = scrubbed
        else:
            event["message"] = scrubbed
    return event


def init_sentry(settings: Settings, **overrides) -> bool:
    """Returns whether monitoring was enabled. `overrides` exists for tests
    (e.g. a capturing transport)."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        before_send=scrub_event,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        **overrides,
    )
    return True
