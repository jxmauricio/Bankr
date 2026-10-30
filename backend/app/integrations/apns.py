"""Send an iOS alert through APNs.

The weekly recap cron (and later, other insights) call `send_alert`. With
no key configured this is a no-op (`skipped`) so local/dev still make the
in-app bell row. The iOS Simulator never receives real APNs; to see the
banner there, `xcrun simctl push` the same payload (see
mobile/scripts/weekly-recap.push.json).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx
from jose import jwt

from app.config import settings

logger = logging.getLogger(__name__)

# APNs JWTs last 60 minutes; mint a new one well before that.
_JWT_TTL_SECONDS = 50 * 60
_cached_jwt: tuple[str, float] | None = None

SENT = "sent"
SKIPPED = "skipped"
FAILED = "failed"
GONE = "gone"


def configured() -> bool:
    return bool(settings.apns_key_id and settings.apns_team_id and settings.apns_auth_key_path)


def send_alert(device_token: str, title: str, body: str, data: dict[str, Any] | None = None) -> str:
    """Push one alert. Returns sent | skipped | failed | gone.

    `gone` means APNs no longer knows this device (app uninstalled, token
    rotated); the caller should drop the row so we stop retrying it.
    """
    token = _jwt()
    if token is None:
        return SKIPPED
    topic = settings.apns_topic or "com.jxmauricio.bankr"
    host = "api.sandbox.push.apple.com" if settings.apns_use_sandbox else "api.push.apple.com"
    payload: dict[str, Any] = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        },
        **(data or {}),
    }
    try:
        with httpx.Client(http2=True, timeout=10) as client:
            response = client.post(
                f"https://{host}/3/device/{device_token}",
                headers={
                    "authorization": f"bearer {token}",
                    "apns-topic": topic,
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                },
                json=payload,
            )
    except Exception:
        logger.exception("APNs request failed")
        return FAILED

    if response.status_code == 200:
        return SENT
    reason = _reason(response)
    if response.status_code in (400, 410) and reason in {"BadDeviceToken", "Unregistered", "ExpiredToken"}:
        return GONE
    logger.warning("APNs rejected push (%s): %s", response.status_code, reason or response.text)
    return FAILED


def _jwt() -> str | None:
    global _cached_jwt
    if not configured():
        return None
    now = time.time()
    if _cached_jwt is not None and now < _cached_jwt[1]:
        return _cached_jwt[0]
    try:
        key = Path(settings.apns_auth_key_path).read_text()
        token = jwt.encode(
            {"iss": settings.apns_team_id, "iat": int(now)},
            key,
            algorithm="ES256",
            headers={"kid": settings.apns_key_id, "alg": "ES256"},
        )
    except Exception:
        logger.exception("Couldn't mint an APNs JWT")
        return None
    _cached_jwt = (token, now + _JWT_TTL_SECONDS)
    return token


def _reason(response: httpx.Response) -> str:
    try:
        return str(response.json().get("reason") or "")
    except Exception:
        return ""
