"""Push: the per-kind switches, and the job that pushes the daily briefing
once a day. Phones register through /devices/push-token (test_devices_push)
and the weekly recap's own cron is in test_weekly_recap."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.db.models import DevicePushToken, InsightLog
from app.integrations import apns
from app.integrations.bank_aggregator import AggregatorTransaction
from app.jobs import briefing_push_job
from app.jobs import daily_briefing_job as briefing_job
from app.jobs import weekly_recap_job as recap_job
from app.services import money_query as mq
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient
from tests.fake_aggregator import FakeAggregatorClient

TOKEN = "aaaaaaaaaaaaaaaa"
# Saturday Oct 31 2026, 9am in New York.
MORNING = datetime(2026, 10, 31, 13, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _models(monkeypatch):
    monkeypatch.setattr(briefing_job, "_client", FakeAgentClient(completions=["Intro."] * 5))
    monkeypatch.setattr(recap_job, "_client", FakeAgentClient(completions=["A week."] * 5))


@pytest.fixture
def sent(monkeypatch):
    """What APNs was asked to send; a token starting "gone" is one APNs no longer knows."""
    out = []

    def fake_send(device_token, title, body, data=None):
        if device_token.startswith("gone"):
            return apns.GONE
        out.append({"token": device_token, "title": title, "body": body, "data": data})
        return apns.SENT

    monkeypatch.setattr(apns, "send_alert", fake_send)
    return out


def _register(client, token=TOKEN, platform="ios"):
    return client.put("/devices/push-token", json={"token": token, "platform": platform})


def _with_review_item(db, user, day=date(2026, 10, 30)):
    sync_user_accounts(
        db,
        user.id,
        "fake-token",
        aggregator=FakeAggregatorClient(
            transactions_by_account={"acc_checking": [AggregatorTransaction("m", "acc_checking", -9.0, day, "SQ *MYSTERY", None, False)]}
        ),
    )


def test_settings_default_on_and_toggle_per_kind(client, db, user):
    assert client.get("/notifications/settings").json() == {"daily_briefing": True, "weekly_recap": True, "device_count": 0}
    _register(client)
    out = client.patch("/notifications/settings", json={"weekly_recap": False}).json()
    assert out == {"daily_briefing": True, "weekly_recap": False, "device_count": 1}
    assert client.get("/notifications/settings").json()["weekly_recap"] is False


def test_briefing_is_pushed_once_from_the_ready_hour(client, db, user, monkeypatch, sent):
    _with_review_item(db, user)
    _register(client)

    monkeypatch.setattr(mq, "_now", lambda: MORNING - timedelta(hours=2))  # 7am: not yet
    assert briefing_push_job.run_due_briefings(db) == 0

    monkeypatch.setattr(mq, "_now", lambda: MORNING)
    assert briefing_push_job.run_due_briefings(db) == 1
    assert briefing_push_job.run_due_briefings(db) == 0

    [push] = sent
    assert push["body"] == "Pick a category for SQ *MYSTERY."
    assert push["data"] == {"type": "daily_briefing", "day": "2026-10-31"}
    log = db.query(InsightLog).filter(InsightLog.type == "daily_briefing").one()
    assert log.delivered_via == "push"


def test_no_push_when_the_app_already_showed_it_or_the_user_turned_it_off(client, db, user, monkeypatch, sent):
    monkeypatch.setattr(mq, "_now", lambda: MORNING)
    _with_review_item(db, user)
    _register(client)

    client.get("/briefing/today")  # seen in the app first
    briefing_push_job.run_due_briefings(db)
    assert sent == []

    client.patch("/notifications/settings", json={"daily_briefing": False})
    monkeypatch.setattr(mq, "_now", lambda: MORNING + timedelta(days=1))
    briefing_push_job.run_due_briefings(db)
    assert sent == []
    assert db.query(InsightLog).filter(InsightLog.type == "daily_briefing").count() == 1


def test_briefing_stays_in_app_when_apns_isnt_configured(client, db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: MORNING)
    _with_review_item(db, user)
    _register(client)

    assert briefing_push_job.run_due_briefings(db) == 1  # apns.send_alert skips: no key in tests
    assert db.query(InsightLog).filter(InsightLog.type == "daily_briefing").one().delivered_via == "in_app"


def test_weekly_recap_push_respects_its_switch(client, db, user, monkeypatch, sent):
    monkeypatch.setattr(mq, "_now", lambda: MORNING)
    _with_review_item(db, user, day=date(2026, 10, 20))
    _register(client)
    client.patch("/notifications/settings", json={"weekly_recap": False})

    assert len(recap_job.run_due_recaps(db, ignore_schedule=True)) == 1
    assert sent == []
    assert db.query(InsightLog).filter(InsightLog.type == "weekly_recap").one().delivered_via == "in_app"


def test_tokens_apns_no_longer_knows_are_forgotten(client, db, user, monkeypatch, sent):
    monkeypatch.setattr(mq, "_now", lambda: MORNING)
    _with_review_item(db, user)
    _register(client)
    _register(client, token="gone-aaaaaaaaaaaa", platform="android")

    briefing_push_job.run_due_briefings(db)

    assert [t for (t,) in db.query(DevicePushToken.token)] == [TOKEN]
    assert len(sent) == 1
