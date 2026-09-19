from app.api.deps import get_aggregator
from app.main import app
from tests.fake_aggregator import FakeAggregatorClient


def _with_fake_aggregator(client):
    app.dependency_overrides[get_aggregator] = lambda: FakeAggregatorClient()
    return client


def test_create_link_token(client):
    _with_fake_aggregator(client)

    response = client.post("/linked-accounts/link-token")

    assert response.status_code == 200
    assert response.json()["link_token"]


def test_link_account_runs_sync_and_returns_summary(client):
    _with_fake_aggregator(client)

    response = client.post("/linked-accounts", json={"public_token": "public-fake-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["linked_account_count"] == 2
    assert body["transactions_synced"] == 3
    assert body["net_worth"] == 2100.0


def test_dashboard_reflects_synced_data(client, monkeypatch):
    from datetime import datetime, timezone

    from app.services import money_query

    # The fake aggregator's transactions are dated Aug 2026; "month" means
    # since the 1st, so pin today inside August.
    monkeypatch.setattr(money_query, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))
    _with_fake_aggregator(client)
    client.post("/linked-accounts", json={"public_token": "public-fake-token"})

    net_worth = client.get("/dashboard/net-worth").json()
    assert net_worth["current"] == 2100.0
    assert [a["balance"] for a in net_worth["accounts"]] == [2500.0, 400.0]

    rollup = client.get("/dashboard/rollup", params={"period": "month"}).json()
    assert rollup["income"] == 3000.0
    assert rollup["spending"] == 165.50
    assert rollup["gain"] == 2834.50
    assert (rollup["start"], rollup["end"]) == ("2026-08-01", "2026-08-20")

    spending = client.get("/dashboard/spending", params={"period": "month"}).json()
    assert spending["total"] == 165.50
    assert len(spending["items"]) == 2


def test_create_goal_then_read_progress(client):
    _with_fake_aggregator(client)
    client.post("/linked-accounts", json={"public_token": "public-fake-token"})

    create_response = client.post(
        "/goals",
        json={"type": "save_amount", "target_amount": 1000.0, "target_date": "2027-01-01"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["starting_amount"] == 2500.0

    progress = client.get("/dashboard/goal-progress").json()
    assert progress["goals"][0]["type"] == "save_amount"
    assert progress["goals"][0]["current_progress_amount"] == 0.0  # no new sync since goal creation


def test_create_goal_keeps_existing_and_rejects_a_sixth(client):
    _with_fake_aggregator(client)
    client.post("/linked-accounts", json={"public_token": "public-fake-token"})

    for i in range(5):
        response = client.post("/goals", json={"type": "save_amount", "target_amount": 1000.0 + i})
        assert response.status_code == 200

    sixth = client.post("/goals", json={"type": "save_amount", "target_amount": 50.0})
    assert sixth.status_code == 422
    progress = client.get("/dashboard/goal-progress").json()
    assert progress["active_count"] == 5


def test_create_goal_rejects_invalid_type(client):
    response = client.post("/goals", json={"type": "buy_a_yacht", "target_amount": 1000.0})
    assert response.status_code == 422


def test_create_goal_rejects_nonpositive_target(client):
    response = client.post("/goals", json={"type": "save_amount", "target_amount": 0})
    assert response.status_code == 422


def test_spending_drilldown_matches_a_chat_source_query(client, monkeypatch):
    from datetime import datetime, timezone

    from app.services import money_query

    monkeypatch.setattr(money_query, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))
    _with_fake_aggregator(client)
    client.post("/linked-accounts", json={"public_token": "public-fake-token"})

    r = client.get("/dashboard/spending", params={"start": "2026-08-01", "end": "2026-08-31", "category": "Dining"})
    body = r.json()
    assert body["total"] == 45.0
    assert [i["merchant_name"] for i in body["items"]] == ["Ramen Spot"]
    assert body["end"] == "2026-08-20"  # capped at today

    bad = client.get("/dashboard/spending", params={"category": "grocries"})
    assert bad.status_code == 422
    assert "Groceries" in bad.json()["detail"]["did_you_mean"]
