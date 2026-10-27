import json

import pytest

from app.agent import claude_agent
from app.config import settings
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
    assert body["sources"] == [{"tool": "get_net_worth", "label": "Net worth · 2 accounts", "query": None, "searched": None}]

    # Only the final resolved text turns are persisted, not the intermediate
    # tool_use/tool_result pair -- see chat_service.py. The source labels
    # (not the raw tool call/result) ride along on the assistant row, with
    # the dollar amounts the reply's figures are cited against.
    messages = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at).all()
    assert len(messages) == 2
    assert messages[1].tool_calls == [
        {"tool": "get_net_worth", "label": "Net worth · 2 accounts", "figures": [400.0, 2100.0, 2500.0]}
    ]
    assert body["citations"] == [{"text": "$2,100", "source": 1}]


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
        {"tool": "web_search", "label": "Searched “current high yield savings rates”", "query": None, "searched": None}
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
    assert body["sources"] == [{"tool": "propose_goal", "label": "Proposed a savings goal", "query": None, "searched": None}]
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
    assert history[1]["sources"] == [{"tool": "propose_goal", "label": "Proposed a savings goal", "query": None, "searched": None}]


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
    assert body["sources"] == [{"tool": "propose_goal", "label": "Proposed a spending tracker", "query": None, "searched": None}]
    assert body["goal_proposal"]["type"] == "track_spending"
    assert body["goal_proposal"]["category"] == "Food & Drink"
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


def test_chat_stream_sends_status_then_the_reply_text_then_done(client, db, user, monkeypatch):
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
    names = [name for name, _ in events]
    assert names == ["status", "status"] + ["delta"] * 5 + ["done"]
    assert events[0][1] == {"label": "Checking your balances…"}
    assert events[1][1] == {"label": "Looking up Dining spending…"}
    assert "".join(data["text"] for name, data in events if name == "delta") == "Your net worth is $2,100."
    done = events[-1][1]
    assert done["reply"] == "Your net worth is $2,100."
    assert done["sources"][0]["tool"] == "get_net_worth"

    # Saved exactly like the non-streaming endpoint.
    messages = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at).all()
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[1].content == "Your net worth is $2,100."


def test_chat_stream_sends_reset_when_the_model_drops_its_text(client, user, monkeypatch):
    """Text written before a tool call isn't the answer: the client is told
    to drop it before the real reply streams."""

    class ThinksAloudClient:
        def run_turn(self, system, tools, history, call_tool, on_text=None):
            on_text("Let me check.")
            on_text(None)
            on_text("All set.")
            return "All set."

    monkeypatch.setattr(claude_agent, "_client", ThinksAloudClient())

    events = _sse_events(client.post("/chat/stream", json={"message": "hi"}))

    assert [name for name, _ in events] == ["delta", "reset", "delta", "done"]
    assert events[-1][1]["reply"] == "All set."


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


def test_cancelled_turn_saves_nothing(db, user, monkeypatch):
    import pytest
    from uuid import uuid4

    from app.agent.claude_agent import TurnCancelled
    from app.services import chat_service

    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(turns=[ScriptedTurn(final_text="Your net worth is $2,100.", tool_calls=[("get_net_worth", {})])]),
    )

    with pytest.raises(TurnCancelled):
        chat_service.send_message(db, user.id, uuid4(), "what's my net worth?", is_cancelled=lambda: True)

    assert db.query(ChatMessage).filter(ChatMessage.user_id == user.id).count() == 0


_ROUNDS = [
    {"input": 1000, "output": 50, "reasoning": None, "cached": 200, "cost": 0.001},
    {"input": 1200, "output": 80, "reasoning": None, "cached": None, "cost": 0.0015},
]


def test_chat_has_no_usage_unless_debug_is_on(client, user, monkeypatch):
    monkeypatch.setattr(claude_agent, "_client", FakeAgentClient(turns=[ScriptedTurn(final_text="Hi!", usage=_ROUNDS)]))

    assert client.post("/chat", json={"message": "hi"}).json()["usage"] is None


def test_chat_debug_sums_usage_across_rounds(client, user, monkeypatch):
    monkeypatch.setattr(settings, "agent_debug", True)
    monkeypatch.setattr(claude_agent, "_client", FakeAgentClient(turns=[ScriptedTurn(final_text="Hi!", usage=_ROUNDS)]))

    usage = client.post("/chat", json={"message": "hi"}).json()["usage"]

    assert usage["rounds"] == 2
    assert usage["input_tokens"] == 2200
    assert usage["output_tokens"] == 130
    assert usage["cached_tokens"] == 200
    assert usage["reasoning_tokens"] is None  # never reported, so unknown rather than 0
    assert usage["cost_usd"] == pytest.approx(0.0025)
    assert usage["model"]


def test_chat_debug_leaves_cost_unknown_when_the_provider_reports_none(client, user, monkeypatch):
    monkeypatch.setattr(settings, "agent_debug", True)
    rounds = [{"input": 10, "output": 5}]
    monkeypatch.setattr(claude_agent, "_client", FakeAgentClient(turns=[ScriptedTurn(final_text="Hi!", usage=rounds)]))

    usage = client.post("/chat", json={"message": "hi"}).json()["usage"]

    assert usage["input_tokens"] == 10
    assert usage["cost_usd"] is None


def test_chat_stream_done_event_carries_usage_in_debug(client, user, monkeypatch):
    monkeypatch.setattr(settings, "agent_debug", True)
    monkeypatch.setattr(claude_agent, "_client", FakeAgentClient(turns=[ScriptedTurn(final_text="Hi!", usage=_ROUNDS)]))

    events = _sse_events(client.post("/chat/stream", json={"message": "hi"}))

    done = next(data for event, data in events if event == "done")
    assert done["usage"]["rounds"] == 2
    assert done["usage"]["cost_usd"] == pytest.approx(0.0025)
