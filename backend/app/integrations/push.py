"""Push notifications to the mobile app, through Expo's push service.

Same adapter shape as WebSearchClient and AgentClient: callers depend on the
PushSender Protocol, never on Expo's API. With push off (EXPO_PUSH_ENABLED
unset, the local-dev default) the sender is a no-op, so the jobs that push
run the same everywhere and only delivery is skipped.
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
# Expo accepts up to 100 messages per request.
_BATCH = 100


@dataclass
class PushMessage:
    token: str
    title: str
    body: str
    # Read by the app when the notification is tapped, e.g. {"kind": "daily_briefing"}.
    data: dict = field(default_factory=dict)


@dataclass
class PushResult:
    sent: int = 0
    # Tokens Expo says no longer reach a device (the app was uninstalled);
    # the caller deletes them.
    dead_tokens: list[str] = field(default_factory=list)


class PushSender(Protocol):
    def send(self, messages: list[PushMessage]) -> PushResult: ...


class NoopPushSender:
    """Push isn't configured: log what would have gone out, send nothing."""

    def send(self, messages: list[PushMessage]) -> PushResult:
        for m in messages:
            logger.info("push disabled; not sending %r", m.title)
        return PushResult()


class ExpoPushSender:
    """https://docs.expo.dev/push-notifications/sending-notifications/"""

    def __init__(self, access_token: str = ""):
        self._headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if access_token:
            self._headers["Authorization"] = f"Bearer {access_token}"

    def send(self, messages: list[PushMessage]) -> PushResult:
        result = PushResult()
        for i in range(0, len(messages), _BATCH):
            batch = messages[i : i + _BATCH]
            response = httpx.post(
                _EXPO_PUSH_URL,
                headers=self._headers,
                json=[{"to": m.token, "title": m.title, "body": m.body, "data": m.data, "sound": "default"} for m in batch],
                timeout=15.0,
            )
            response.raise_for_status()
            # One ticket per message, in order.
            for message, ticket in zip(batch, response.json().get("data") or []):
                if ticket.get("status") == "ok":
                    result.sent += 1
                elif (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                    result.dead_tokens.append(message.token)
                else:
                    logger.warning("push to a device failed: %s", ticket.get("message"))
        return result


def build_push_sender() -> PushSender:
    from app.config import settings

    if settings.expo_push_enabled:
        return ExpoPushSender(access_token=settings.expo_access_token)
    return NoopPushSender()
