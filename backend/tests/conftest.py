"""Test fixtures.

Uses a real local Postgres database (bankr_test), not sqlite/mocks -- the
schema leans on Postgres-specific types (JSONB, UUID) so a lighter-weight
substitute would test something different from what actually runs.
Tables are truncated before every test rather than wrapped in a rollback,
since app code under test calls db.commit() itself.

Setup: createdb -O bankr bankr_test  (see backend/README.md)
"""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault(
    "DATABASE_URL", "postgresql://bankr:bankr@localhost:5432/bankr_test"
)
os.environ.setdefault("SESSION_JWT_SECRET", "test-secret")
os.environ.setdefault(
    "TOKEN_ENCRYPTION_KEY", "ziMCX2zuXm-wqPP1MbdpWti2J4HxbDturtJ47-6W-Co="
)

from app.auth import get_current_user  # noqa: E402
from app.db.base import Base, get_db  # noqa: E402
from app.db import models  # noqa: E402,F401
from app.main import app  # noqa: E402

TEST_DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _truncate_tables():
    with engine.begin() as conn:
        table_names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user(db):
    from app.db.models import User

    u = User(email=f"{uuid4()}@example.com", apple_sub=str(uuid4()))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def client(db, user):
    def _override_get_db():
        yield db

    def _override_get_current_user():
        return user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()
