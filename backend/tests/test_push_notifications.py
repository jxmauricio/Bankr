"""Push: registering a phone, the per-kind switches, and the job that pushes
the daily briefing and the weekly recap once each."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.db.models import InsightLog, PushDevice
from app.integrations.bank_aggregator import AggregatorTransaction
from app.integrations.push import ExpoPushSender, NoopPushSender, PushMessage
from app.jobs import daily_briefing_job as briefing_job
from app.jobs import notifications_job
from app.jobs import weekly_recap_job as recap_job
from app.services import money_query as mq
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient
from tests.fake_aggregator import FakeAggregatorClient
from tests.fake_push import FakePushSender

TOKEN = "ExponentPushToken[abc123]"
# Saturday Oct 31 2026, 9am in New York.
MORNING = datetime(2026, 10, 31, 13, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _models(monkeypatch):
    monkeypatch.setattr(briefing_job, "_client", FakeAgentClient(completions=["Intro."] * 5))
    monkeypatch.setattr(recap_job, "_client", FakeAgentClient(completions=["A week."] * 5))


def _register(client, token=TOKEN, platform="ios"):
    return client.post("/notifications/devices", json={"token": token, "platform": platform})


def _with_review_item(db, user, day=date(2026, 10, 30)):
    sync_user_accounts(
        db,
        user.id,
        "fake-token",
        aggregator=FakeAggregatorClient(
            transactions_by_account={"acc_checking": [AggregatorTransaction("m", "acc_checking", -9.0, day, "SQ *MYSTERY", None, False)]}
        ),
    )


# --- registration and settings -----------------------------------------------


def test_register_device_validates_and_is_idempotent(client, db, user):
    assert _register(client).status_code == 204
    assert _register(client).status_code == 204
    device = db.query(PushDevice).one()
    assert (device.user_id, device.token, device.platform) == (user.id, TOKEN, "ios")

    assert _register(client, token="not-a-token").status_code == 422
    assert client.post("/notifications/devices", json={"token": TOKEN, "platform": "windows"}).status_code == 422


def test_a_token_follows_whoever_signs_in_on_the_phone(client, db, user):
    from app.db.models import User
    from app.services import push_service

    other = User(email="other@example.com")
    db.add(other)
    db.commit()
    push_service.register_device(db, other.id, TOKEN, "ios")

    _register(client)
    assert db.query(PushDevice).one().user_id == user.id

    client.post("/notifications/devices/remove", json={"token": TOKEN})
    assert db.query(PushDevice).count() == 0


def test_settings_default_on_and_toggle_per_kind(client, db, user):
    assert client.get("/notifications/settings").json() == {"daily_briefing": True, "weekly_recap": True, "device_count": 0}
    _register(client)
    out = client.patch("/notifications/settings", json={"weekly_recap": False}).json()
    assert out == {"daily_briefing": True, "weekly_recap": False, "device_count": 1}
    assert client.get("/notifications/settings").json()["weekly_recap"] is False


# --- the job -----------------------------------------------------------------


def test_briefing_is_pushed_once_from_the_ready_hour(client, db, user, monkeypatch):
    _with_review_item(db, user)
    _register(client)
    sender = FakePushSender()

    monkeypatch.setattr(mq, "_now", lambda: MORNING - timedelta(hours=2))  # 7am: not yet
    assert notifications_job.run_notifications_job(db, sender)["daily_briefing"] == 0

    monkeypatch.setattr(mq, "_now", lambda: MORNING)
    assert notifications_job.run_notifications_job(db, sender)["daily_briefing"] == 1
    assert notifications_job.run_notifications_job(db, sender)["daily_briefing"] == 0

    briefing_pushes = [m for m in sender.sent if m.data["kind"] == "daily_briefing"]
    assert len(briefing_pushes) == 1
    assert briefing_pushes[0].body == "Pick a category for SQ *MYSTERY."
    assert briefing_pushes[0].data == {"kind": "daily_briefing", "day": "2026-10-31"}
    log = db.query(InsightLog).filter(InsightLog.type == "daily_briefing").one()
    assert log.delivered_via == "push"


def test_no_push_when_the_app_already_showed_it_or_the_user_turned_it_off(client, db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: MORNING)
    _with_review_item(db, user)
    _register(client)
    sender = FakePushSender()

    client.get("/briefing/today")  # seen in the app first
    notifications_job.run_notifications_job(db, sender)
    assert [m for m in sender.sent if m.data["kind"] == "daily_briefing"] == []

    client.patch("/notifications/settings", json={"daily_briefing": False, "weekly_recap": False})
    monkeypatch.setattr(mq, "_now", lambda: MORNING + timedelta(days=1))
    notifications_job.run_notifications_job(db, sender)
    assert sender.sent == []


def test_weekly_recap_is_pushed_once(client, db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: MORNING)
    _with_review_item(db, user, day=date(2026, 10, 20))
    _register(client)
    client.patch("/notifications/settings", json={"daily_briefing": False})
    sender = FakePushSender()

    assert notifications_job.run_notifications_job(db, sender)["weekly_recap"] == 1
    assert notifications_job.run_notifications_job(db, sender)["weekly_recap"] == 0
    [push] = sender.sent
    assert push.data == {"kind": "weekly_recap", "week_start": "2026-10-19"}
    assert push.title == "$9.00 more went out than came in"
    assert db.query(InsightLog).filter(InsightLog.type == "weekly_recap").one().delivered_via == "push"


def test_tokens_for_uninstalled_apps_are_forgotten(client, db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: MORNING)
    _with_review_item(db, user)
    _register(client)
    _register(client, token="ExponentPushToken[gone]", platform="android")

    notifications_job.run_notifications_job(db, FakePushSender(dead_tokens={"ExponentPushToken[gone]"}))

    assert [t for (t,) in db.query(PushDevice.token)] == [TOKEN]


# --- senders -----------------------------------------------------------------


def test_noop_sender_sends_nothing():
    assert NoopPushSender().send([PushMessage(TOKEN, "t", "b")]).sent == 0


def test_expo_sender_reads_tickets(monkeypatch):
    posted = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"status": "ok"}, {"status": "error", "details": {"error": "DeviceNotRegistered"}}]}

    def fake_post(url, headers, json, timeout):
        posted.update(url=url, headers=headers, json=json)
        return Response()

    monkeypatch.setattr("app.integrations.push.httpx.post", fake_post)
    result = ExpoPushSender(access_token="secret").send([PushMessage(TOKEN, "t", "b"), PushMessage("ExponentPushToken[gone]", "t", "b")])

    assert (result.sent, result.dead_tokens) == (1, ["ExponentPushToken[gone]"])
    assert posted["url"] == "https://exp.host/--/api/v2/push/send"
    assert posted["headers"]["Authorization"] == "Bearer secret"
    assert posted["json"][0] == {"to": TOKEN, "title": "t", "body": "b", "data": {}, "sound": "default"}
