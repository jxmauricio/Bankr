import json

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


def _sse_events(response) -> list[tuple[str, dict]]:
    events = []
    for block in response.text.split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        if not lines:
            continue
        event = next(line[len("event: ") :] for line in lines if line.startswith("event: "))
        data = next(line[len("data: ") :] for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


def test_chat_stream_sends_status_then_the_reply(client, db, user, monkeypatch):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(
            turns=[
                ScriptedTurn(
                    final_text="Your net worth is $2,100.",
                    tool_calls=[("get_net_worth", {}), ("get_spending", {"category": "Dining"})],
                ),
            ]
        ),
    )

    response = client.post("/chat/stream", json={"message": "what's my net worth?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(response)
    assert [name for name, _ in events] == ["status", "status", "done"]
    assert events[0][1] == {"label": "Checking your balances…"}
    assert events[1][1] == {"label": "Looking up Dining spending…"}
    done = events[2][1]
    assert done["reply"] == "Your net worth is $2,100."
    assert done["sources"][0]["tool"] == "get_net_worth"

    # Saved exactly like the non-streaming endpoint.
    messages = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at).all()
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[1].content == "Your net worth is $2,100."


def test_chat_stream_reports_a_failed_turn_as_an_error_event(client, user, monkeypatch):
    class ExplodingClient:
        def run_turn(self, *args, **kwargs):
            raise RuntimeError("provider down")

    monkeypatch.setattr(claude_agent, "_client", ExplodingClient())

    response = client.post("/chat/stream", json={"message": "hi"})

    assert response.status_code == 200
    events = _sse_events(response)
    assert [name for name, _ in events] == ["error"]
    assert "couldn't respond" in events[0][1]["message"]
