"""Bankr-as-MCP-server: auth, token scoping, and tool calls over /mcp."""

import json

import pytest
from fastapi.testclient import TestClient

from app.auth import issue_mcp_token, issue_session_token
from app.db import base as db_base
from app.main import app
from app.services.sync_service import sync_user_accounts
from tests.conftest import TestSessionLocal
from tests.fake_aggregator import FakeAggregatorClient

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(method: str, params: dict | None = None, id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}


@pytest.fixture
def mcp_client(monkeypatch):
    monkeypatch.setattr(db_base, "SessionLocal", TestSessionLocal)
    with TestClient(app) as c:  # `with` runs the lifespan that starts the MCP session manager
        yield c


def tool_payload(response) -> dict:
    result = response.json()["result"]
    assert not result.get("isError"), result
    return json.loads(result["content"][0]["text"])


def auth(user) -> dict:
    return {**HEADERS, "Authorization": f"Bearer {issue_mcp_token(user.id)}"}


def test_mcp_requires_a_token(mcp_client):
    r = mcp_client.post("/mcp", json=rpc("tools/list"), headers=HEADERS)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_mcp_rejects_a_session_token(mcp_client, user):
    headers = {**HEADERS, "Authorization": f"Bearer {issue_session_token(user.id)}"}
    assert mcp_client.post("/mcp", json=rpc("tools/list"), headers=headers).status_code == 401


def test_mcp_token_cannot_call_the_rest_api(user):
    # Uses the real get_current_user (no dependency override).
    with TestClient(app) as c:
        r = c.get("/dashboard/net-worth", headers={"Authorization": f"Bearer {issue_mcp_token(user.id)}"})
    assert r.status_code == 401


def test_mint_mcp_token_endpoint(client, user):
    from app.auth import verify_mcp_token

    r = client.post("/auth/mcp-token")
    assert r.status_code == 200
    assert verify_mcp_token(r.json()["mcp_token"]) == user.id


def test_tools_list_is_read_only_subset(mcp_client, user):
    r = mcp_client.post("/mcp", json=rpc("tools/list"), headers=auth(user))
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {
        "get_net_worth",
        "get_cash_flow",
        "get_spending",
        "compare_spending",
        "find_transactions",
        "get_goal_progress",
        "get_recent_transactions",
        "get_unusual_transactions",
    }


def test_tool_call_returns_the_callers_data(mcp_client, db, user):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    r = mcp_client.post(
        "/mcp", json=rpc("tools/call", {"name": "get_net_worth", "arguments": {}}), headers=auth(user)
    )
    assert r.status_code == 200
    assert tool_payload(r)["net_worth"] == 2100.0  # 2500 assets - 400 liabilities


def test_tool_call_is_scoped_to_the_token_user(mcp_client, db, user):
    from uuid import uuid4

    from app.db.models import User

    other = User(email=f"{uuid4()}@example.com", apple_sub=str(uuid4()))
    db.add(other)
    db.commit()
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())

    r = mcp_client.post(
        "/mcp", json=rpc("tools/call", {"name": "get_net_worth", "arguments": {}}), headers=auth(other)
    )
    assert tool_payload(r)["net_worth"] is None


def test_other_paths_are_not_swallowed_by_the_mount(mcp_client):
    assert mcp_client.get("/health").json() == {"status": "ok"}
    assert mcp_client.get("/nope").status_code == 404
