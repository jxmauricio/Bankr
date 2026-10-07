"""The in-app insights feed: newest first, scoped to the user, mark read."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.models import InsightLog, User


def _log(db, user_id, message, minutes_ago, type_="unusual_transaction", key=None):
    log = InsightLog(
        user_id=user_id,
        type=type_,
        message=message,
        dedupe_key=key,
        delivered_via="in_app",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )
    db.add(log)
    db.commit()
    return log


def test_feed_read_and_scoping(client, db, user):
    other = User(email=f"{uuid4()}@example.com", apple_sub=str(uuid4()))
    db.add(other)
    db.commit()
    old = _log(db, user.id, "old", 60, type_="budget_overspend", key="budget_overspend:flex:2026-09:over")
    _log(db, user.id, "new", 1)
    _log(db, other.id, "not yours", 0)

    feed = client.get("/insights").json()
    assert feed["unread_count"] == 2
    assert [i["message"] for i in feed["insights"]] == ["new", "old"]
    assert feed["insights"][1]["subject_id"] == "flex"

    r = client.post(f"/insights/{old.id}/read")
    assert r.json()["read"] is True
    assert client.get("/insights", params={"unread_only": True}).json()["unread_count"] == 1

    assert client.post("/insights/read-all").status_code == 204
    assert client.get("/insights").json()["unread_count"] == 0

    foreign = db.query(InsightLog).filter(InsightLog.user_id == other.id).one()
    assert client.post(f"/insights/{foreign.id}/read").status_code == 404
