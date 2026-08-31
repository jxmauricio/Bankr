from uuid import uuid4

from app.db.models import ChatMessage, User
from app.services import chat_service
from tests.fake_agent_client import FakeAgentClient, ScriptedTurn


def _send(client, monkeypatch, message, reply, conversation_id=None):
    from app.agent import claude_agent

    monkeypatch.setattr(claude_agent, "_client", FakeAgentClient(turns=[ScriptedTurn(final_text=reply)]))
    body = {"message": message}
    if conversation_id:
        body["conversation_id"] = str(conversation_id)
    return client.post("/chat", json=body).json()


def test_list_conversations_returns_newest_first_with_a_preview(client, monkeypatch):
    first = _send(client, monkeypatch, "what's my net worth?", "It's $2,100.")
    second = _send(client, monkeypatch, "how about spending?", "You spent $400.")

    response = client.get("/chat/conversations")

    assert response.status_code == 200
    body = response.json()
    assert [c["conversation_id"] for c in body] == [second["conversation_id"], first["conversation_id"]]
    assert body[0]["preview"] == "how about spending?"
    assert body[0]["message_count"] == 2  # one user + one assistant message
    assert body[1]["preview"] == "what's my net worth?"


def test_list_conversations_truncates_a_long_first_message(client, monkeypatch):
    long_message = "x" * 500
    _send(client, monkeypatch, long_message, "ok")

    body = client.get("/chat/conversations").json()

    assert len(body[0]["preview"]) == 120


def test_list_conversations_only_returns_the_current_users_conversations(db, user, client, monkeypatch):
    other_user = User(email=f"{uuid4()}@example.com", apple_sub=str(uuid4()))
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    db.add(
        ChatMessage(
            user_id=other_user.id, conversation_id=uuid4(), role="user", content="someone else's message"
        )
    )
    db.commit()

    _send(client, monkeypatch, "my message", "my reply")

    body = client.get("/chat/conversations").json()

    assert len(body) == 1
    assert body[0]["preview"] == "my message"


def test_get_conversation_returns_full_history_with_sources(client, monkeypatch):
    from app.agent import claude_agent

    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(
            turns=[
                ScriptedTurn(final_text="Your net worth is $2,100.", tool_calls=[("get_net_worth", {})]),
            ]
        ),
    )
    first = client.post("/chat", json={"message": "what's my net worth?"}).json()

    response = client.get(f"/chat/conversations/{first['conversation_id']}")

    assert response.status_code == 200
    messages = response.json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "what's my net worth?"
    assert messages[0]["sources"] == []
    assert messages[1]["content"] == "Your net worth is $2,100."
    assert messages[1]["sources"] == [{"tool": "get_net_worth", "label": "Net worth"}]


def test_get_conversation_404s_for_an_unknown_or_foreign_conversation(client):
    response = client.get(f"/chat/conversations/{uuid4()}")

    assert response.status_code == 404


def test_get_conversation_404s_for_another_users_conversation(db, user, client):
    other_user = User(email=f"{uuid4()}@example.com", apple_sub=str(uuid4()))
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    other_conversation_id = uuid4()
    db.add(
        ChatMessage(
            user_id=other_user.id, conversation_id=other_conversation_id, role="user", content="not yours"
        )
    )
    db.commit()

    response = client.get(f"/chat/conversations/{other_conversation_id}")

    assert response.status_code == 404


def test_list_conversations_service_function_directly(db, user):
    db.add(ChatMessage(user_id=user.id, conversation_id=uuid4(), role="user", content="hi"))
    db.commit()

    result = chat_service.list_conversations(db, user.id)

    assert len(result) == 1
    assert result[0]["message_count"] == 1
