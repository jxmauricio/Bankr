import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.db.base import get_db
from app.db.models import User
from app.main import app
from app.scripts.reset_password import ResetError, reset_password


def _make_user(db, email: str, password: str = "old-password") -> User:
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    return user


def _login(db, email: str, password: str) -> int:
    app.dependency_overrides[get_db] = lambda: db
    try:
        return TestClient(app).post("/auth/login", json={"email": email, "password": password}).status_code
    finally:
        app.dependency_overrides.clear()


def test_reset_lets_user_log_in_with_new_password_only(db):
    _make_user(db, "friend@example.com")

    reset_password(db, "friend@example.com", "brand-new-pw")

    assert _login(db, "friend@example.com", "brand-new-pw") == 200
    assert _login(db, "friend@example.com", "old-password") == 401


def test_reset_matches_email_ignoring_case_and_whitespace(db):
    _make_user(db, "Friend@Example.com")

    user = reset_password(db, "  friend@example.COM ", "brand-new-pw")

    assert user.email == "Friend@Example.com"


def test_reset_rejects_unknown_email(db):
    with pytest.raises(ResetError, match="No account"):
        reset_password(db, "nobody@example.com", "brand-new-pw")


def test_reset_rejects_short_password_and_leaves_old_one(db):
    _make_user(db, "friend@example.com")

    with pytest.raises(ResetError, match="at least 8"):
        reset_password(db, "friend@example.com", "short")

    assert _login(db, "friend@example.com", "old-password") == 200
