"""Spending health uses complete-month averages and published guidelines."""

import pytest

from app.services import money_query as mq
from app.services.spending_health import _points, _save_tone, _save_verdict, _spend_tone, _spend_verdict, spending_health
from app.services.sync_service import sync_user_accounts
from tests.golden_ledger import EXPECTED, FROZEN_NOW, golden_aggregator

TODAY = FROZEN_NOW.date()


@pytest.fixture
def ledger(db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: FROZEN_NOW)
    sync_user_accounts(db, user.id, "golden-token", aggregator=golden_aggregator())
    return user


def test_health_uses_complete_months_and_scores_rent_food_saving(db, ledger):
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

    # Aug rent 1800 + PG&E 85 is 31.4% of income: just over the 30% bar.
    rent = next(c for c in health["categories"] if c["name"] == "Rent & Utilities")
    assert rent["amount"] == 1885.00
    assert rent["recommended_pct"] == 30
    assert rent["source"] == "HUD / CFPB"
    assert rent["tone"] == "ok"

    food = next(c for c in health["categories"] if c["name"] == "Food & Drink")
    assert food["amount"] == EXPECTED["food_last_month"]
    assert food["recommended_pct"] == 15
    assert food["tone"] == "good"
    assert food["verdict"].startswith("Healthy")

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
    assert {c["name"] for c in health["categories"]}.isdisjoint({"Transfer In", "Transfer Out"})


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
    assert body["snapshots"][1]["name"] == "Rent & Utilities"
    assert body["snapshots"][2]["name"] == "Food & Drink"
    assert "as_of" in body


def test_score_averages_four_metrics(db, ledger):
    health = spending_health(db, ledger.id)
    metrics = {m["id"]: m for m in health["metrics"]}
    assert list(metrics) == ["saved", "emergency_fund", "Loan Payments", "Rent & Utilities"]
    assert metrics["saved"]["value"] == health["saved_pct"]
    assert metrics["Rent & Utilities"]["value"] == next(c["pct"] for c in health["categories"] if c["name"] == "Rent & Utilities")
    assert metrics["emergency_fund"]["unit"] == "months"
    scored = [m["points"] for m in health["metrics"] if m["points"] is not None]
    assert scored and health["score"] == round(sum(scored) / len(scored))
    assert 0 <= health["score"] <= 100


def test_points_are_full_at_the_guideline_and_fall_off_past_it():
    assert _points(37, 20, True) == 100
    assert _points(15, 20, True) == 75
    assert _points(30, 30, False) == 100
    assert _points(34.5, 30, False) == pytest.approx(70)
    assert _points(45, 30, False) == 0
    assert _points(None, 30, False) is None


def test_groceries_are_a_need_and_eating_out_a_want(db, ledger):
    # August: rent & PG&E 1885 + transportation 181 + groceries 275.75 are
    # needs; the flight (net 300) and Nopa 60 are wants.
    needs, wants, _ = spending_health(db, ledger.id)["buckets"]
    assert needs["amount"] == 2341.75
    assert wants["amount"] == 360.00
