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


def test_dashboard_reflects_synced_data(client):
    _with_fake_aggregator(client)
    client.post("/linked-accounts", json={"public_token": "public-fake-token"})

    net_worth = client.get("/dashboard/net-worth").json()
    assert net_worth["current"] == 2100.0

    rollup = client.get("/dashboard/rollup", params={"period": "month"}).json()
    assert rollup["income"] == 3000.0
    assert rollup["spending"] == 165.50
    assert rollup["gain"] == 2834.50

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
    assert progress["type"] == "save_amount"
    assert progress["current_progress_amount"] == 0.0  # no new sync since goal creation


def test_create_goal_rejects_invalid_type(client):
    response = client.post("/goals", json={"type": "buy_a_yacht", "target_amount": 1000.0})
    assert response.status_code == 422


def test_create_goal_rejects_nonpositive_target(client):
    response = client.post("/goals", json={"type": "save_amount", "target_amount": 0})
    assert response.status_code == 422
