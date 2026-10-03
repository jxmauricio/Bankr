"""Caps on paid LLM usage: tool rounds per message, history sent per
message, and insights re-phrased on every sync."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.agent.agent_client import ToolSpec
from app.agent.providers import MAX_TOOL_ROUNDS, AnthropicAgentClient, OpenRouterAgentClient
from app.db.models import ChatMessage, Goal, InsightLog
from app.jobs import insights_job
from app.services import chat_service
from app.services.goal_service import create_goal
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient
from tests.fake_aggregator import FakeAggregatorClient

_TOOLS = [ToolSpec(name="get_net_worth", description="", parameters={"type": "object", "properties": {}})]


def test_openai_compatible_tool_loop_stops_at_the_cap(monkeypatch):
    client = OpenRouterAgentClient(api_key="key", model="some/model")
    calls = []

    def always_wants_a_tool(**kwargs):
        calls.append(kwargs)
        final = kwargs.get("tool_choice") == "none"
        tool_calls = None if final else [
            SimpleNamespace(id=f"call-{len(calls)}", function=SimpleNamespace(name="get_net_worth", arguments="{}"))
        ]
        message = SimpleNamespace(
            content="Here's what I found." if final else None,
            tool_calls=tool_calls,
            model_dump=lambda exclude_none=True: {"role": "assistant", "content": ""},
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(client._client.chat.completions, "create", always_wants_a_tool)

    reply = client.run_turn("system", _TOOLS, [{"role": "user", "content": "hi"}], call_tool=lambda n, a: {})

    assert reply == "Here's what I found."
    assert len(calls) == MAX_TOOL_ROUNDS + 1
    assert all("tool_choice" not in c for c in calls[:-1])
    assert calls[-1]["tool_choice"] == "none"


def test_anthropic_tool_loop_stops_at_the_cap(monkeypatch):
    client = AnthropicAgentClient(api_key="key", model="claude-sonnet-5")
    calls = []

    def always_wants_a_tool(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="partial answer"),
                SimpleNamespace(type="tool_use", id=f"tu-{len(calls)}", name="get_net_worth", input={}),
            ],
            stop_reason="tool_use",
        )

    monkeypatch.setattr(client._client.messages, "create", always_wants_a_tool)

    reply = client.run_turn("system", _TOOLS, [{"role": "user", "content": "hi"}], call_tool=lambda n, a: {})

    assert reply == "partial answer"
    assert len(calls) == MAX_TOOL_ROUNDS + 1
    assert calls[-1]["tool_choice"] == {"type": "none"}


def test_history_sent_to_the_model_is_capped_and_starts_on_a_user_turn(db, user):
    conversation_id = uuid4()
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    total = chat_service.MAX_HISTORY_MESSAGES + 5  # odd overflow, so the raw cut lands on an assistant turn
    for i in range(total):
        db.add(
            ChatMessage(
                user_id=user.id,
                conversation_id=conversation_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"message {i}",
                created_at=start + timedelta(seconds=i),
            )
        )
    db.commit()

    history = chat_service._conversation_history(db, user.id, conversation_id)

    assert len(history) <= chat_service.MAX_HISTORY_MESSAGES
    assert history[0]["role"] == "user"
    assert history[-1]["content"] == f"message {total - 1}"


def test_goal_drift_insight_is_phrased_once_not_on_every_sync(db, user, monkeypatch):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    create_goal(db, user.id, "save", target_amount=1000.0, target_date=date.today() + timedelta(days=30))
    goal = db.query(Goal).filter(Goal.user_id == user.id).one()
    goal.created_at = goal.created_at - timedelta(days=20)
    db.commit()

    # Exactly one scripted completion: a second LLM call would raise.
    monkeypatch.setattr(insights_job, "_client", FakeAgentClient(completions=["You're behind pace."]))

    first = insights_job.run_insights_job(db, user.id)
    second = insights_job.run_insights_job(db, user.id)

    assert len(first) == 1
    assert second == []
    assert db.query(InsightLog).filter(InsightLog.user_id == user.id).count() == 1


def test_dedupe_keys():
    unusual = insights_job.InsightCandidate(type="unusual_transaction", data={"transaction_id": "t1"})
    drift = insights_job.InsightCandidate(type="goal_drift", data={"id": "g1"})
    monday, sunday, next_monday = date(2026, 9, 28), date(2026, 10, 4), date(2026, 10, 5)

    assert insights_job._dedupe_key(unusual, monday) == insights_job._dedupe_key(unusual, next_monday)
    assert insights_job._dedupe_key(drift, monday) == insights_job._dedupe_key(drift, sunday)
    assert insights_job._dedupe_key(drift, monday) != insights_job._dedupe_key(drift, next_monday)
