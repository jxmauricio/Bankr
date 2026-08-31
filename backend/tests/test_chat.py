from app.agent import claude_agent
from app.db.models import ChatMessage
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient, ScriptedTurn
from tests.fake_aggregator import FakeAggregatorClient
from tests.fake_web_search import FakeWebSearchClient


def test_chat_reply_with_no_tool_use(client, db, user, monkeypatch):
    monkeypatch.setattr(claude_agent, "_client", FakeAgentClient(turns=[ScriptedTurn(final_text="Hello!")]))

    response = client.post("/chat", json={"message": "hi"})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hello!"
    assert body["sources"] == []

    messages = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at).all()
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "hi"
    assert messages[1].content == "Hello!"
    assert messages[1].tool_calls is None


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
    body = response.json()
    assert body["reply"] == "Your net worth is $2,100."
    assert body["sources"] == [{"tool": "get_net_worth", "label": "Net worth"}]

    # Only the final resolved text turns are persisted, not the intermediate
    # tool_use/tool_result pair -- see chat_service.py. The source labels
    # (not the raw tool call/result) ride along on the assistant row.
    messages = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at).all()
    assert len(messages) == 2
    assert messages[1].tool_calls == [{"tool": "get_net_worth", "label": "Net worth"}]


def test_chat_resolves_a_web_search_call_before_replying(client, db, monkeypatch):
    fake_search = FakeWebSearchClient()
    monkeypatch.setattr(claude_agent, "_search_client", fake_search)
    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(
            turns=[
                ScriptedTurn(
                    final_text="Savings rates are running around 4.5% APY right now.",
                    tool_calls=[("web_search", {"query": "current high yield savings rates"})],
                ),
            ]
        ),
    )

    response = client.post("/chat", json={"message": "what's a good savings rate right now?"})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Savings rates are running around 4.5% APY right now."
    assert body["sources"] == [
        {"tool": "web_search", "label": "Searched “current high yield savings rates”"}
    ]
    assert fake_search.queries == ["current high yield savings rates"]


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
