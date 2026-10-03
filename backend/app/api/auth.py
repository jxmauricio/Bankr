from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

import secrets

from app.auth import (
    get_current_user,
    hash_password,
    issue_mcp_token,
    issue_session_token,
    verify_apple_identity_token,
    verify_password,
)
from app.config import settings
from app.db.base import get_db
from app.db.models import User
from app.rate_limit import limit_auth_by_ip

router = APIRouter(prefix="/auth", tags=["auth"])


class AppleSignInRequest(BaseModel):
    identity_token: str


class SessionResponse(BaseModel):
    session_token: str


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    invite_code: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/apple", response_model=SessionResponse)
def sign_in_with_apple(body: AppleSignInRequest, db: Session = Depends(get_db)) -> SessionResponse:
    claims = verify_apple_identity_token(body.identity_token)
    apple_sub = claims["sub"]
    email = claims.get("email")

    user = db.query(User).filter(User.apple_sub == apple_sub).one_or_none()
    if user is None:
        user = User(apple_sub=apple_sub, email=email or f"{apple_sub}@privaterelay.appleid.com")
        db.add(user)
        db.commit()
        db.refresh(user)

    return SessionResponse(session_token=issue_session_token(user.id))


def _valid_invite_code(code: str) -> bool:
    if not settings.invite_codes:
        return True
    return any(secrets.compare_digest(code.strip(), valid) for valid in settings.invite_codes)


@router.post(
    "/signup",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_auth_by_ip)],
)
def sign_up(body: SignUpRequest, db: Session = Depends(get_db)) -> SessionResponse:
    if not _valid_invite_code(body.invite_code):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A valid invite code is required to sign up")

    if len(body.password) < 8:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password must be at least 8 characters")

    existing = db.query(User).filter(User.email == body.email).one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    return SessionResponse(session_token=issue_session_token(user.id))


@router.post("/login", response_model=SessionResponse, dependencies=[Depends(limit_auth_by_ip)])
def login(body: LoginRequest, db: Session = Depends(get_db)) -> SessionResponse:
    user = db.query(User).filter(User.email == body.email).one_or_none()
    if user is None or user.password_hash is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    return SessionResponse(session_token=issue_session_token(user.id))


class McpTokenResponse(BaseModel):
    mcp_token: str


@router.post("/mcp-token", response_model=McpTokenResponse)
def create_mcp_token(user: User = Depends(get_current_user)) -> McpTokenResponse:
    """Mint a token for connecting an external MCP client to /mcp."""
    return McpTokenResponse(mcp_token=issue_mcp_token(user.id))
