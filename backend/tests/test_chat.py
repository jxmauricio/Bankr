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
    assert body["sources"] == [{"tool": "get_net_worth", "label": "Net worth · 2 accounts", "query": None}]

    # Only the final resolved text turns are persisted, not the intermediate
    # tool_use/tool_result pair -- see chat_service.py. The source labels
    # (not the raw tool call/result) ride along on the assistant row.
    messages = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at).all()
    assert len(messages) == 2
    assert messages[1].tool_calls == [{"tool": "get_net_worth", "label": "Net worth · 2 accounts"}]


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
        {"tool": "web_search", "label": "Searched “current high yield savings rates”", "query": None}
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


def test_chat_propose_goal_returns_a_confirmable_proposal_without_writing(client, db, user, monkeypatch):
    from app.db.models import Goal
    from app.services.goal_service import create_goal

    create_goal(db, user.id, "save", 1000.0, None)
    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(
            turns=[
                ScriptedTurn(
                    final_text="I can set a $5,000 savings goal if you confirm the card.",
                    tool_calls=[
                        (
                            "propose_goal",
                            {"type": "save", "name": "Savings", "target_amount": 5000, "target_date": "2027-12-31"},
                        )
                    ],
                ),
            ]
        ),
    )

    response = client.post("/chat", json={"message": "I want to save $5000 by the end of 2027"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == [{"tool": "propose_goal", "label": "Proposed a savings goal", "query": None}]
    assert body["goal_proposal"]["type"] == "save"
    assert body["goal_proposal"]["name"] == "Savings"
    assert body["goal_proposal"]["target_amount"] == 5000.0
    assert body["goal_proposal"]["target_date"] == "2027-12-31"
    assert body["goal_proposal"]["replaces_existing"] is False
    assert body["goal_proposal"]["at_limit"] is False

    # The tool drafts only -- confirming in the UI is what POSTs /goals.
    active = db.query(Goal).filter(Goal.user_id == user.id, Goal.status == "active").all()
    assert len(active) == 1
    assert float(active[0].target_amount) == 1000.0

    history = client.get(f"/chat/conversations/{body['conversation_id']}").json()
    assert history[1]["goal_proposal"]["target_amount"] == 5000.0
    assert history[1]["sources"] == [{"tool": "propose_goal", "label": "Proposed a savings goal", "query": None}]


def test_chat_propose_spending_tracker_returns_category_and_window(client, db, user, monkeypatch):
    from app.db.models import Goal

    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(
            turns=[
                ScriptedTurn(
                    final_text="I can track dining this month if you confirm the card.",
                    tool_calls=[
                        (
                            "propose_goal",
                            {"type": "track_spending", "category": "eating out", "window": "this_month"},
                        )
                    ],
                ),
            ]
        ),
    )

    response = client.post("/chat", json={"message": "I'm spending too much on eating out"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == [{"tool": "propose_goal", "label": "Proposed a spending tracker", "query": None}]
    assert body["goal_proposal"]["type"] == "track_spending"
    assert body["goal_proposal"]["category"] == "Dining"
    assert body["goal_proposal"]["window"] == "this_month"
    assert body["goal_proposal"]["target_amount"] == 0.0
    assert db.query(Goal).filter(Goal.user_id == user.id).count() == 0
