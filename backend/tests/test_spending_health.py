"""Spending health uses complete-month averages and published guidelines."""

import pytest

from app.services import money_query as mq
from app.services.spending_health import _save_tone, _save_verdict, _spend_tone, _spend_verdict, spending_health
from app.services.sync_service import sync_user_accounts
from tests.golden_ledger import EXPECTED, FROZEN_NOW, golden_aggregator

TODAY = FROZEN_NOW.date()


@pytest.fixture
def ledger(db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: FROZEN_NOW)
    sync_user_accounts(db, user.id, "golden-token", aggregator=golden_aggregator())
    return user


def test_health_uses_complete_months_and_scores_rent_groceries_saving(db, ledger):
    last = mq.resolve_window(TODAY, "last_month")
    income = mq.income_query(db, ledger.id, last)["total_income"]
    spend = mq.spend_query(db, ledger.id, last, group_by="category")
    health = spending_health(db, ledger.id)

    assert health["partial"] is False
    assert health["months_used"] == 1
    assert health["end"] == "2026-08-31"
    assert health["income"] == income
    assert health["spending"] == spend["total_spent"]
    assert health["saved"] == pytest.approx(income - spend["total_spent"], abs=0.01)

    rent = next(c for c in health["categories"] if c["name"] == "Rent & Housing")
    assert rent["amount"] == 1800.00
    assert rent["recommended_pct"] == 30
    assert rent["source"] == "HUD / CFPB"
    assert rent["tone"] == "good"
    assert rent["verdict"].startswith("Healthy")

    groc = next(c for c in health["categories"] if c["name"] == "Groceries")
    assert groc["amount"] == EXPECTED["groceries_last_month"]
    assert groc["recommended_pct"] == 10
    assert groc["tone"] == "good"

    saved = health["snapshots"][0]
    assert saved["id"] == "saved"
    assert saved["recommended_pct"] == 20
    assert saved["higher_is_better"] is True
    assert saved["tone"] == "good"
    assert saved["verdict"].startswith("Healthy")

    needs, wants, saved_b = health["buckets"]
    assert needs["recommended_pct"] == 50
    assert wants["recommended_pct"] == 30
    assert saved_b["amount"] == health["saved"]
    assert {c["name"] for c in health["categories"]}.isdisjoint({"Transfer"})


def test_spend_under_the_guideline_is_healthy():
    assert _spend_tone(28.6, 30) == "good"
    assert _spend_tone(30, 30) == "good"
    assert _spend_tone(32, 30) == "ok"
    assert _spend_tone(36, 30) == "high"
    assert _spend_verdict(28.6, 30).startswith("Healthy")


def test_saving_in_a_reasonable_range_is_healthy():
    assert _save_tone(20, 20) == "good"
    assert _save_tone(19.7, 20) == "good"
    assert _save_tone(15, 20) == "good"
    assert _save_tone(12, 20) == "ok"
    assert _save_tone(8, 20) == "high"
    assert _save_verdict(19.7, 20).startswith("Healthy")


def test_health_endpoint_returns_the_same_shape(client, db, ledger):
    body = client.get("/dashboard/health").json()
    assert body["snapshots"][0]["id"] == "saved"
    assert body["snapshots"][1]["name"] == "Rent & Housing"
    assert body["snapshots"][2]["name"] == "Groceries"
    assert "as_of" in body
