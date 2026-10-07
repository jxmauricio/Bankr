"""Recurring detection: real schedules are found, noise isn't, and the
user's confirm/dismiss choices survive re-detection."""

from datetime import date, timedelta

import pytest

from app.db.models import InsightLog, RecurringSeries
from app.integrations.bank_aggregator import AggregatorTransaction
from app.jobs import insights_job
from app.services import money_query as mq
from app.services.recurring_service import add_months, detect_recurring, merchant_key
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient
from tests.fake_aggregator import FakeAggregatorClient

TODAY = date(2026, 9, 19)


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    monkeypatch.setattr(mq, "today_for_user", lambda db, user_id: TODAY)


def _t(txn_id, day, amount, merchant, raw):
    return AggregatorTransaction(txn_id, "acc_checking", amount, day, merchant, raw, False)


def _monthly(prefix, merchant, amount, raw, months=6, day=5, last_amount=None):
    out = []
    for i in range(months):
        d = add_months(date(2026, 9, day), -i)
        if d > TODAY:
            continue
        amt = last_amount if (i == 0 and last_amount is not None) else amount
        out.append(_t(f"{prefix}{i}", d, amt, merchant, raw))
    return out


def _sync(db, user, txns):
    fake = FakeAggregatorClient(transactions_by_account={"acc_checking": txns})
    sync_user_accounts(db, user.id, "fake-token", aggregator=fake)
    return fake


def _by_name(db, user):
    return {s.merchant_key: s for s in db.query(RecurringSeries).filter(RecurringSeries.user_id == user.id)}


def test_merchant_key_normalizes():
    assert merchant_key("NETFLIX.COM 866-579-7172") == "netflix"
    assert merchant_key("Spotify USA #123") == "spotify usa"


def test_detects_monthly_weekly_yearly_and_income(db, user):
    txns = [
        *_monthly("nf", "Netflix", -15.49, "ENTERTAINMENT_TV_AND_MOVIES"),
        *_monthly("rent", "Greystar", -1800.0, "RENT_AND_UTILITIES_RENT", day=1),
        # Weekly, same amount.
        *[_t(f"gym{i}", TODAY - timedelta(days=7 * i), -12.0, "Climbing Gym", "PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS") for i in range(6)],
        # Yearly: two charges a year apart.
        _t("amz1", date(2025, 9, 10), -139.0, "Amazon Prime", "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES"),
        _t("amz2", date(2026, 9, 10), -139.0, "Amazon Prime", "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES"),
        # Biweekly paycheck.
        *[_t(f"pay{i}", date(2026, 9, 11) - timedelta(days=14 * i), 2500.0, "Employer Inc", "INCOME_WAGES") for i in range(6)],
        # Noise: irregular coffee at random amounts.
        _t("c1", date(2026, 9, 1), -4.5, "Blue Bottle", "FOOD_AND_DRINK_COFFEE"),
        _t("c2", date(2026, 9, 3), -11.0, "Blue Bottle", "FOOD_AND_DRINK_COFFEE"),
        _t("c3", date(2026, 9, 17), -6.25, "Blue Bottle", "FOOD_AND_DRINK_COFFEE"),
        _t("c4", date(2026, 8, 2), -23.0, "Blue Bottle", "FOOD_AND_DRINK_COFFEE"),
    ]
    _sync(db, user, txns)
    detect_recurring(db, user.id)
    found = _by_name(db, user)

    assert found["netflix"].cadence == "monthly"
    assert found["greystar"].cadence == "monthly" and found["greystar"].kind == "bill"
    assert found["climbing gym"].cadence == "weekly"
    assert found["amazon prime"].cadence == "yearly"
    assert found["employer"].cadence == "biweekly" and found["employer"].kind == "income"
    assert "blue bottle" not in found
    assert found["netflix"].next_expected_date == date(2026, 10, 5)
    assert all(s.status == "suggested" for s in found.values())


def test_user_choices_survive_redetection(client, db, user):
    _sync(db, user, _monthly("nf", "Netflix", -15.49, "ENTERTAINMENT_TV_AND_MOVIES")
          + _monthly("hulu", "Hulu", -7.99, "ENTERTAINMENT_TV_AND_MOVIES"))
    detect_recurring(db, user.id)
    found = _by_name(db, user)

    r = client.patch(f"/recurring/{found['netflix'].id}", json={"status": "confirmed", "kind": "subscription"})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    client.patch(f"/recurring/{found['hulu'].id}", json={"status": "dismissed"})

    detect_recurring(db, user.id)
    db.expire_all()
    found = _by_name(db, user)
    assert found["netflix"].status == "confirmed"
    assert found["hulu"].status == "dismissed"

    overview = client.get("/recurring").json()
    assert [s["name"] for s in overview["series"]] == ["Netflix"]
    assert overview["monthly"]["subscriptions"] == 15.49
    assert overview["upcoming"][0] == {
        "series_id": str(found["netflix"].id),
        "name": "Netflix",
        "kind": "subscription",
        "status": "confirmed",
        "date": "2026-10-05",
        "amount": 15.49,
    }


def test_price_change_becomes_one_insight(client, db, user, monkeypatch):
    monkeypatch.setattr(insights_job, "_client", FakeAgentClient(completions=["Netflix went up to $17.99."]))
    _sync(db, user, _monthly("nf", "Netflix", -15.49, "ENTERTAINMENT_TV_AND_MOVIES", last_amount=-17.99))
    detect_recurring(db, user.id)
    series = _by_name(db, user)["netflix"]
    assert float(series.typical_amount) == 15.49 and float(series.last_amount) == 17.99

    # Only confirmed series raise a price-change nudge.
    insights_job.run_insights_job(db, user.id)
    assert db.query(InsightLog).filter(InsightLog.type == "price_change").count() == 0

    client.patch(f"/recurring/{series.id}", json={"status": "confirmed"})
    insights_job.run_insights_job(db, user.id)
    insights_job.run_insights_job(db, user.id)
    assert db.query(InsightLog).filter(InsightLog.type == "price_change").count() == 1


def test_resync_runs_detection(client, db, user):
    from app.api.deps import get_aggregator
    from app.main import app

    fake = FakeAggregatorClient(transactions_by_account={"acc_checking": _monthly("nf", "Netflix", -15.49, "ENTERTAINMENT_TV_AND_MOVIES")})
    app.dependency_overrides[get_aggregator] = lambda: fake
    assert client.post("/linked-accounts", json={"public_token": "public-x"}).status_code == 200
    assert "netflix" in _by_name(db, user)


def test_bills_never_raise_price_changes_and_arent_unusual(client, db, user):
    from app.agent import tools
    from app.services.recurring_service import price_changes

    txns = _monthly("pge", "PG&E", -80.0, "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY", last_amount=-120.0)
    _sync(db, user, txns)
    detect_recurring(db, user.id)
    series = _by_name(db, user)["pg e"]
    client.patch(f"/recurring/{series.id}", json={"status": "confirmed"})
    assert series.kind == "bill"
    assert price_changes(db, user.id) == []

    expected = tools.recurring_merchant_keys(db, user.id)
    assert "pg e" in expected
