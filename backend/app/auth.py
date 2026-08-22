"""Auth: email/password (web) + Sign in with Apple (iOS, currently shelved).

Both flows converge on the same session issuance: upsert/verify a User row,
then hand back a short-lived session JWT that the client attaches to every
subsequent API call.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import httpx
from fastapi import Depends, HTTPException, status
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


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.session_jwt_secret,
            algorithms=[settings.session_jwt_algorithm],
        )
    except (JWTError, ExpiredSignatureError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session") from exc

    user = db.get(User, UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user
