from app.db.base import get_db
from app.db.models import User
from app.main import app


def test_signup_creates_user_and_returns_session_token(db):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    response = client.post("/auth/signup", json={"email": "new@example.com", "password": "hunter22"})

    assert response.status_code == 201
    assert response.json()["session_token"]
    assert db.query(User).filter(User.email == "new@example.com").one_or_none() is not None
    app.dependency_overrides.clear()


def test_signup_rejects_duplicate_email(db):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    client.post("/auth/signup", json={"email": "dupe@example.com", "password": "hunter22"})

    response = client.post("/auth/signup", json={"email": "dupe@example.com", "password": "hunter22"})

    assert response.status_code == 409
    app.dependency_overrides.clear()


def test_signup_rejects_short_password(db):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    response = client.post("/auth/signup", json={"email": "short@example.com", "password": "abc"})

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_login_with_correct_password_returns_session_token(db):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    client.post("/auth/signup", json={"email": "login@example.com", "password": "hunter22"})

    response = client.post("/auth/login", json={"email": "login@example.com", "password": "hunter22"})

    assert response.status_code == 200
    assert response.json()["session_token"]
    app.dependency_overrides.clear()


def test_login_with_wrong_password_is_rejected(db):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    client.post("/auth/signup", json={"email": "wrongpw@example.com", "password": "hunter22"})

    response = client.post("/auth/login", json={"email": "wrongpw@example.com", "password": "nope1234"})

    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_login_with_unknown_email_is_rejected(db):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    response = client.post("/auth/login", json={"email": "ghost@example.com", "password": "hunter22"})

    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_signup_requires_invite_code_when_configured(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "signup_invite_codes", "friends-beta, second-code")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    missing = client.post("/auth/signup", json={"email": "a@example.com", "password": "hunter22"})
    wrong = client.post(
        "/auth/signup", json={"email": "a@example.com", "password": "hunter22", "invite_code": "nope"}
    )
    right = client.post(
        "/auth/signup", json={"email": "a@example.com", "password": "hunter22", "invite_code": "second-code"}
    )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert right.status_code == 201
    app.dependency_overrides.clear()


def test_login_is_rate_limited_per_ip(db):
    from fastapi.testclient import TestClient

    from app.rate_limit import auth_limiter

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    statuses = [
        client.post("/auth/login", json={"email": "ghost@example.com", "password": "hunter22"}).status_code
        for _ in range(auth_limiter.max_calls + 1)
    ]

    assert statuses[:-1] == [401] * auth_limiter.max_calls
    assert statuses[-1] == 429
    app.dependency_overrides.clear()


def test_production_refuses_dev_placeholder_secrets():
    import pytest

    from app.config import Settings

    with pytest.raises(RuntimeError, match="SESSION_JWT_SECRET"):
        Settings(
            environment="production",
            database_url="postgresql://x",
            session_jwt_secret="change-me-in-prod",
            token_encryption_key="k",
            cors_allowed_origins="https://bankr.example.com",
        ).check_production_ready()

    Settings(
        environment="production",
        database_url="postgresql://x",
        session_jwt_secret="x" * 32,
        token_encryption_key="k",
        cors_allowed_origins="https://bankr.example.com",
    ).check_production_ready()
