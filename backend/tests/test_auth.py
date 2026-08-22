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
