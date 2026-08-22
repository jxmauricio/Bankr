from app.agent import claude_agent
from app.db.models import ChatMessage
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient, ScriptedTurn
from tests.fake_aggregator import FakeAggregatorClient


def test_chat_reply_with_no_tool_use(client, db, user, monkeypatch):
    monkeypatch.setattr(claude_agent, "_client", FakeAgentClient(turns=[ScriptedTurn(final_text="Hello!")]))

    response = client.post("/chat", json={"message": "hi"})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hello!"

    messages = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at).all()
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "hi"
    assert messages[1].content == "Hello!"


def test_chat_resolves_a_tool_call_before_replying(client, db, user, monkeypatch):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())

    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(
            turns=[
                ScriptedTurn(final_text="Your net worth is $2,100.", tool_calls=[("get_net_worth", {})]),
            ]
        ),
    )

    response = client.post("/chat", json={"message": "what's my net worth?"})

    assert response.status_code == 200
    assert response.json()["reply"] == "Your net worth is $2,100."

    # Only the final resolved text turns are persisted, not the intermediate
    # tool_use/tool_result pair -- see chat_service.py.
    messages = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).all()
    assert len(messages) == 2


def test_chat_continues_the_same_conversation(client, monkeypatch):
    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(turns=[ScriptedTurn(final_text="Hi there!"), ScriptedTurn(final_text="Sure, go on.")]),
    )

    first = client.post("/chat", json={"message": "hi"}).json()
    second = client.post(
        "/chat", json={"message": "can I ask something?", "conversation_id": first["conversation_id"]}
    ).json()

    assert second["conversation_id"] == first["conversation_id"]
    assert second["reply"] == "Sure, go on."
