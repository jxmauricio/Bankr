"""Auth: email/password (web) + Sign in with Apple (iOS, currently shelved).

Both flows converge on the same session issuance: upsert/verify a User row,
then hand back a short-lived session JWT that the client attaches to every
subsequent API call.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import bcrypt
import httpx
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import get_db
from app.db.models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

_bearer = HTTPBearer()


def _fetch_apple_jwks() -> dict:
    response = httpx.get(APPLE_KEYS_URL, timeout=10)
    response.raise_for_status()
    return response.json()


def verify_apple_identity_token(identity_token: str) -> dict:
    """Verify an Apple identity token and return its claims (includes `sub`, `email`)."""
    jwks = _fetch_apple_jwks()
    try:
        header = jwt.get_unverified_header(identity_token)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed identity token") from exc

    key = next((k for k in jwks["keys"] if k["kid"] == header.get("kid")), None)
    if key is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown signing key")

    try:
        claims = jwt.decode(
            identity_token,
            key,
            algorithms=["RS256"],
            audience=settings.apple_client_id,
            issuer=APPLE_ISSUER,
        )
    except (JWTError, ExpiredSignatureError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid identity token") from exc

    return claims


def issue_session_token(user_id: UUID) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.session_jwt_ttl_seconds)
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at},
        settings.session_jwt_secret,
        algorithm=settings.session_jwt_algorithm,
    )


MCP_SCOPE = "mcp"


def issue_mcp_token(user_id: UUID) -> str:
    """Long-lived, read-only-scoped token for connecting an external MCP
    client (e.g. the user's own Claude) to /mcp. Carries scope="mcp" so it
    is accepted only there -- get_current_user rejects it, so a token pasted
    into a third-party client can't be replayed against the full REST API
    (chat, goals, bank linking)."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.mcp_token_ttl_seconds)
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at, "scope": MCP_SCOPE},
        settings.session_jwt_secret,
        algorithm=settings.session_jwt_algorithm,
    )


def verify_mcp_token(token: str) -> UUID | None:
    """Return the user id for a valid MCP-scoped token, else None."""
    try:
        payload = jwt.decode(token, settings.session_jwt_secret, algorithms=[settings.session_jwt_algorithm])
        if payload.get("scope") != MCP_SCOPE:
            return None
        return UUID(payload["sub"])
    except (JWTError, ExpiredSignatureError, KeyError, ValueError):
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
    x_timezone: str | None = Header(default=None),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.session_jwt_secret,
            algorithms=[settings.session_jwt_algorithm],
        )
    except (JWTError, ExpiredSignatureError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session") from exc

    if payload.get("scope") == MCP_SCOPE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MCP tokens cannot be used for the REST API")

    user = db.get(User, UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    _remember_timezone(db, user, x_timezone)
    return user


def _remember_timezone(db: Session, user: User, tz_name: str | None) -> None:
    """Clients send their IANA zone as X-Timezone on every request; keep it
    so "this month" / "last week" are anchored where the user actually is
    (see app/services/money_query.py). Invalid values are ignored."""
    if not tz_name or tz_name == user.timezone:
        return
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return
    user.timezone = tz_name
    db.commit()
