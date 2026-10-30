from app.db.models import DevicePushToken, User
from uuid import uuid4


def test_register_replaces_owner_of_the_same_token(client, db, user):
    other = User(email=f"{uuid4()}@example.com", apple_sub=str(uuid4()))
    db.add(other)
    db.commit()
    db.add(DevicePushToken(user_id=other.id, token="aaaaaaaaaaaaaaaa", platform="ios"))
    db.commit()

    assert client.put("/devices/push-token", json={"token": "aaaaaaaaaaaaaaaa", "platform": "ios"}).json() == {
        "ok": True
    }
    row = db.query(DevicePushToken).filter(DevicePushToken.token == "aaaaaaaaaaaaaaaa").one()
    assert row.user_id == user.id

    client.put("/devices/push-token", json={"token": "bbbbbbbbbbbbbbbb"})
    assert {t.token for t in db.query(DevicePushToken).filter(DevicePushToken.user_id == user.id)} == {
        "aaaaaaaaaaaaaaaa",
        "bbbbbbbbbbbbbbbb",
    }

    assert client.delete("/devices/push-token").status_code == 204
    assert db.query(DevicePushToken).filter(DevicePushToken.user_id == user.id).count() == 0


def test_short_push_token_is_rejected(client):
    assert client.put("/devices/push-token", json={"token": "short"}).status_code == 422
