"""Bankr-as-MCP-server: auth, token scoping, and tool calls over /mcp, the
OAuth 2.1 flow Claude/ChatGPT connectors use, and write-scope proposals."""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

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
    challenge = r.headers["www-authenticate"]
    assert challenge.startswith("Bearer ")
    assert 'resource_metadata="http://testserver/.well-known/oauth-protected-resource/mcp"' in challenge
    assert 'scope="read write"' in challenge


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


# --- OAuth 2.1 (Claude / ChatGPT custom connectors) ---

from app.db.models import McpGrant, McpProposal, Rule, Transaction  # noqa: E402
from app.db.seed_categories import seed_default_categories  # noqa: E402

CALLBACK = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
RESOURCE = "http://testserver/mcp"


def session_headers(user) -> dict:
    return {"Authorization": f"Bearer {issue_session_token(user.id)}"}


def register(c, redirect_uris=(CALLBACK,), name="Claude") -> str:
    r = c.post("/oauth/register", json={"redirect_uris": list(redirect_uris), "client_name": name})
    assert r.status_code == 201, r.text
    assert r.json()["token_endpoint_auth_method"] == "none"
    return r.json()["client_id"]


def authorize(c, client_id, redirect_uri=CALLBACK, **overrides):
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "state": "xyz",
        "scope": "read write",
        "resource": RESOURCE,
        **overrides,
    }
    return c.get("/oauth/authorize", params={k: v for k, v in params.items() if v is not None}, follow_redirects=False)


def consent(c, user, client_id, write=False, approve=True, redirect_uri=CALLBACK) -> dict:
    """Authorize, then decide on the consent page; returns the query the
    browser is sent back to the client with."""
    r = authorize(c, client_id, redirect_uri)
    assert r.status_code == 302, r.text
    location = urlsplit(r.headers["location"])
    assert location.path == "/oauth/consent"
    request_id = parse_qs(location.query)["request"][0]

    info = c.get(f"/oauth/requests/{request_id}", headers=session_headers(user)).json()
    assert info["client_name"] in ("Claude", "Claude Code")
    assert info["requested_scopes"] == ["read", "write"]

    r = c.post(
        f"/oauth/requests/{request_id}/decision",
        json={"approve": approve, "write": write},
        headers=session_headers(user),
    )
    assert r.status_code == 200, r.text
    back = urlsplit(r.json()["redirect_to"])
    assert f"{back.scheme}://{back.netloc}{back.path}" == redirect_uri
    return {k: v[0] for k, v in parse_qs(back.query).items()}


def exchange(c, client_id, code, verifier=VERIFIER, redirect_uri=CALLBACK):
    return c.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
            "resource": RESOURCE,
        },
    )


def connect(c, user, write=False) -> dict:
    client_id = register(c)
    query = consent(c, user, client_id, write=write)
    r = exchange(c, client_id, query["code"])
    assert r.status_code == 200, r.text
    return {**r.json(), "client_id": client_id}


def bearer(token: str) -> dict:
    return {**HEADERS, "Authorization": f"Bearer {token}"}


def call(c, token, name, arguments=None):
    return c.post("/mcp", json=rpc("tools/call", {"name": name, "arguments": arguments or {}}), headers=bearer(token))


def test_protected_resource_metadata(mcp_client):
    for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
        meta = mcp_client.get(path).json()
        assert meta["resource"] == RESOURCE
        assert meta["authorization_servers"] == ["http://testserver"]
        assert meta["scopes_supported"] == ["read", "write"]


def test_authorization_server_metadata(mcp_client):
    meta = mcp_client.get("/.well-known/oauth-authorization-server").json()
    assert meta["issuer"] == "http://testserver"
    assert meta["authorization_endpoint"] == "http://testserver/oauth/authorize"
    assert meta["token_endpoint"] == "http://testserver/oauth/token"
    assert meta["registration_endpoint"] == "http://testserver/oauth/register"
    assert meta["code_challenge_methods_supported"] == ["S256"]
    # What Claude checks before it uses a Client ID Metadata Document.
    assert meta["client_id_metadata_document_supported"] is True
    assert "none" in meta["token_endpoint_auth_methods_supported"]
    assert meta["authorization_response_iss_parameter_supported"] is True


def test_registration_rejects_unsafe_redirects(mcp_client):
    r = mcp_client.post("/oauth/register", json={"redirect_uris": ["http://evil.example.com/cb"]})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_redirect_uri"


def test_full_flow_issues_a_read_token(mcp_client, user):
    client_id = register(mcp_client)
    query = consent(mcp_client, user, client_id)
    assert query["state"] == "xyz"
    assert query["iss"] == "http://testserver"

    r = exchange(mcp_client, client_id, query["code"])
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    tokens = r.json()
    assert tokens["token_type"] == "Bearer"
    assert tokens["scope"] == "read"
    assert tokens["refresh_token"]

    names = {t["name"] for t in mcp_client.post("/mcp", json=rpc("tools/list"), headers=bearer(tokens["access_token"])).json()["result"]["tools"]}
    assert "get_net_worth" in names
    assert not names & {"propose_goal", "propose_rule", "propose_budget_move", "propose_recategorization"}


def test_token_exchange_requires_the_pkce_verifier(mcp_client, user):
    client_id = register(mcp_client)
    code = consent(mcp_client, user, client_id)["code"]
    r = exchange(mcp_client, client_id, code, verifier="w" * 64)
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


def test_a_code_works_once_and_a_replay_revokes_the_connection(mcp_client, db, user):
    client_id = register(mcp_client)
    code = consent(mcp_client, user, client_id)["code"]
    tokens = exchange(mcp_client, client_id, code).json()
    r = exchange(mcp_client, client_id, code)
    assert r.json()["error"] == "invalid_grant"
    assert call(mcp_client, tokens["access_token"], "get_net_worth").status_code == 401


def test_code_is_bound_to_its_client(mcp_client, user):
    client_id = register(mcp_client)
    other = register(mcp_client, name="Other")
    code = consent(mcp_client, user, client_id)["code"]
    assert exchange(mcp_client, other, code).json()["error"] == "invalid_grant"


def test_authorize_requires_pkce_and_a_registered_redirect(mcp_client):
    client_id = register(mcp_client)
    # Bad redirect: shown here, never redirected to.
    r = authorize(mcp_client, client_id, redirect_uri="https://evil.example.com/cb")
    assert r.status_code == 400
    # No PKCE: the error goes back to the (registered) client.
    r = authorize(mcp_client, client_id, code_challenge=None)
    assert r.status_code == 302
    error = parse_qs(urlsplit(r.headers["location"]).query)
    assert error["error"] == ["invalid_request"] and error["state"] == ["xyz"]
    # A token for some other server.
    r = authorize(mcp_client, client_id, resource="https://elsewhere.example.com/mcp")
    assert parse_qs(urlsplit(r.headers["location"]).query)["error"] == ["invalid_target"]


def test_denying_sends_access_denied(mcp_client, user):
    client_id = register(mcp_client)
    assert consent(mcp_client, user, client_id, approve=False)["error"] == "access_denied"


def test_client_id_metadata_document_with_any_loopback_port(mcp_client, monkeypatch, user):
    from app import mcp_oauth

    url = "https://claude.ai/oauth/claude-code-client-metadata"
    monkeypatch.setattr(
        mcp_oauth,
        "fetch_client_metadata",
        lambda u: {
            "client_id": u,
            "client_name": "Claude Code",
            "redirect_uris": ["http://localhost/callback", "http://127.0.0.1/callback"],
            "token_endpoint_auth_method": "none",
        },
    )
    redirect = "http://localhost:53682/callback"
    code = consent(mcp_client, user, url, redirect_uri=redirect)["code"]
    assert exchange(mcp_client, url, code, redirect_uri=redirect).status_code == 200

    # A document that claims to be another client is refused.
    monkeypatch.setattr(mcp_oauth, "fetch_client_metadata", lambda u: {"client_id": "https://x.example/c", "redirect_uris": [CALLBACK]})
    assert authorize(mcp_client, url).status_code == 400


def test_refresh_rotates_the_refresh_token(mcp_client, user):
    tokens = connect(mcp_client, user)
    form = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": tokens["client_id"]}
    r = mcp_client.post("/oauth/token", data=form)
    assert r.status_code == 200
    fresh = r.json()
    assert fresh["refresh_token"] != tokens["refresh_token"]
    assert call(mcp_client, fresh["access_token"], "get_net_worth").status_code == 200
    # The old refresh token is spent.
    assert mcp_client.post("/oauth/token", data=form).json()["error"] == "invalid_grant"


def test_oauth_token_cannot_call_the_rest_api(mcp_client, user):
    tokens = connect(mcp_client, user, write=True)
    r = mcp_client.get("/dashboard/net-worth", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 401


def test_token_for_another_resource_is_rejected(mcp_client, user, monkeypatch):
    tokens = connect(mcp_client, user)
    from app.config import settings

    monkeypatch.setattr(settings, "public_api_url", "https://api.other.example")
    assert call(mcp_client, tokens["access_token"], "get_net_worth").status_code == 401


def test_read_scope_cannot_call_write_tools(mcp_client, user):
    tokens = connect(mcp_client, user)
    r = call(mcp_client, tokens["access_token"], "propose_rule", {"merchant": "Ramen", "category": "Restaurants"})
    assert r.status_code == 403
    challenge = r.headers["www-authenticate"]
    assert 'error="insufficient_scope"' in challenge and 'scope="write"' in challenge
    # Ordinary reads still work after the body was inspected and replayed.
    assert call(mcp_client, tokens["access_token"], "get_net_worth").status_code == 200


def test_settings_lists_and_revokes_connections(mcp_client, user):
    tokens = connect(mcp_client, user, write=True)
    listing = mcp_client.get("/mcp/grants", headers=session_headers(user)).json()
    assert listing["server_url"] == RESOURCE
    [grant] = listing["grants"]
    assert grant["client_name"] == "Claude"
    assert grant["scopes"] == ["read", "write"]
    assert grant["redirect_host"] == "claude.ai"

    assert mcp_client.delete(f"/mcp/grants/{grant['id']}", headers=session_headers(user)).status_code == 204
    assert call(mcp_client, tokens["access_token"], "get_net_worth").status_code == 401
    form = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}
    assert mcp_client.post("/oauth/token", data=form).json()["error"] == "invalid_grant"
    assert mcp_client.get("/mcp/grants", headers=session_headers(user)).json()["grants"] == []


def test_cannot_revoke_someone_elses_connection(mcp_client, db, user):
    from uuid import uuid4

    from app.db.models import User

    connect(mcp_client, user)
    other = User(email=f"{uuid4()}@example.com")
    db.add(other)
    db.commit()
    grant = db.query(McpGrant).one()
    assert mcp_client.delete(f"/mcp/grants/{grant.id}", headers=session_headers(other)).status_code == 404


def test_rfc7009_revocation(mcp_client, user):
    tokens = connect(mcp_client, user)
    assert mcp_client.post("/oauth/revoke", data={"token": tokens["refresh_token"]}).status_code == 200
    assert call(mcp_client, tokens["access_token"], "get_net_worth").status_code == 401


def test_legacy_minted_token_is_read_only(mcp_client, user):
    names = {t["name"] for t in mcp_client.post("/mcp", json=rpc("tools/list"), headers=auth(user)).json()["result"]["tools"]}
    assert "propose_goal" not in names
    r = mcp_client.post(
        "/mcp", json=rpc("tools/call", {"name": "propose_goal", "arguments": {"type": "save"}}), headers=auth(user)
    )
    assert r.status_code == 403


# --- Write scope: proposals, never direct writes ---


@pytest.fixture
def writer(mcp_client, db, user):
    seed_default_categories(db)
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    return connect(mcp_client, user, write=True)["access_token"]


def test_write_scope_lists_the_propose_tools(mcp_client, writer):
    names = {t["name"] for t in mcp_client.post("/mcp", json=rpc("tools/list"), headers=bearer(writer)).json()["result"]["tools"]}
    assert {"propose_goal", "propose_rule", "propose_budget_move", "propose_recategorization"} <= names
    assert not any("trade" in n or "invest" in n for n in names)


def test_propose_rule_waits_for_the_user(mcp_client, db, user, writer):
    result = tool_payload(call(mcp_client, writer, "propose_rule", {"merchant": "Ramen", "category": "fun"}))
    assert result["status"] == "pending_user_confirmation"
    assert "confirm" in result["message"]
    assert db.query(Rule).count() == 0  # nothing written yet

    [pending] = mcp_client.get("/proposals", headers=session_headers(user)).json()["proposals"]
    assert pending["id"] == result["proposal_id"]
    assert pending["kind"] == "rule" and pending["source"] == "Claude"
    assert pending["summary"] == "Always put “Ramen” in Entertainment & Recreation"

    # The same proposal twice is stored once.
    again = tool_payload(call(mcp_client, writer, "propose_rule", {"merchant": "Ramen", "category": "fun"}))
    assert again["proposal_id"] == result["proposal_id"]

    r = mcp_client.post(f"/proposals/{pending['id']}/confirm", headers=session_headers(user))
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    assert db.query(Rule).count() == 1
    assert mcp_client.get("/proposals", headers=session_headers(user)).json()["proposals"] == []


def test_propose_goal_then_dismiss(mcp_client, db, user, writer):
    result = tool_payload(
        call(mcp_client, writer, "propose_goal", {"type": "save", "target_amount": 5000, "name": "Emergency fund"})
    )
    assert result["summary"] == "Save $5,000.00 for Emergency fund"
    r = mcp_client.post(f"/proposals/{result['proposal_id']}/dismiss", headers=session_headers(user))
    assert r.json()["status"] == "dismissed"
    assert db.query(McpProposal).one().status == "dismissed"
    # Already resolved: can't be confirmed afterwards.
    assert mcp_client.post(f"/proposals/{result['proposal_id']}/confirm", headers=session_headers(user)).status_code == 404


def test_propose_goal_confirm_creates_the_goal(mcp_client, db, user, writer):
    from app.db.models import Goal

    result = tool_payload(call(mcp_client, writer, "propose_goal", {"type": "save", "target_amount": 1200, "name": "Trip"}))
    assert db.query(Goal).count() == 0
    mcp_client.post(f"/proposals/{result['proposal_id']}/confirm", headers=session_headers(user))
    goal = db.query(Goal).one()
    assert goal.name == "Trip" and float(goal.target_amount) == 1200


def test_propose_recategorization(mcp_client, db, user, writer):
    txn = db.query(Transaction).filter(Transaction.aggregator_transaction_id == "txn_dining").one()
    before = txn.bankr_category_id
    result = tool_payload(
        call(mcp_client, writer, "propose_recategorization", {"transaction_id": str(txn.id), "category": "Groceries"})
    )
    assert result["status"] == "pending_user_confirmation"
    db.expire_all()
    assert db.get(Transaction, txn.id).bankr_category_id == before

    mcp_client.post(f"/proposals/{result['proposal_id']}/confirm", headers=session_headers(user))
    db.expire_all()
    changed = db.get(Transaction, txn.id)
    assert changed.bankr_category_id != before and changed.category_source == "manual"


def test_invalid_proposals_are_not_stored(mcp_client, db, writer):
    result = tool_payload(call(mcp_client, writer, "propose_rule", {"merchant": "Ramen", "category": "nope"}))
    assert "error" in result
    result = tool_payload(call(mcp_client, writer, "propose_recategorization", {"transaction_id": "nope", "category": "Groceries"}))
    assert "error" in result
    result = tool_payload(call(mcp_client, writer, "propose_budget_move", {"from_line": "Groceries", "to_line": "Restaurants", "amount": 50}))
    assert "error" in result  # no budget set up
    assert db.query(McpProposal).count() == 0


def test_a_proposal_that_no_longer_applies_stays_pending(mcp_client, db, user, writer):
    txn = db.query(Transaction).filter(Transaction.aggregator_transaction_id == "txn_dining").one()
    result = tool_payload(
        call(mcp_client, writer, "propose_recategorization", {"transaction_id": str(txn.id), "category": "Groceries"})
    )
    db.delete(txn)
    db.commit()
    r = mcp_client.post(f"/proposals/{result['proposal_id']}/confirm", headers=session_headers(user))
    assert r.status_code == 422
    assert db.query(McpProposal).one().status == "pending"


def test_proposals_are_private(mcp_client, db, writer):
    from uuid import uuid4

    from app.db.models import User

    result = tool_payload(call(mcp_client, writer, "propose_rule", {"merchant": "Ramen", "category": "fun"}))
    other = User(email=f"{uuid4()}@example.com")
    db.add(other)
    db.commit()
    assert mcp_client.get("/proposals", headers=session_headers(other)).json()["proposals"] == []
    assert mcp_client.post(f"/proposals/{result['proposal_id']}/confirm", headers=session_headers(other)).status_code == 404
