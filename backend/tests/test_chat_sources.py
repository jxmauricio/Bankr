"""Unit coverage for claude_agent's tool-call -> source-label mapping and
run_agent_turn's sources return value, separate from test_chat.py's
HTTP-level coverage."""

from datetime import datetime, timezone

import pytest

from app.agent.claude_agent import _describe_tool_call, run_agent_turn
from app.agent import claude_agent
from app.services import money_query
from tests.fake_agent_client import FakeAgentClient, ScriptedTurn


@pytest.mark.parametrize(
    "name,tool_input,expected",
    [
        ("get_net_worth", {}, "Net worth"),
        ("get_goal_progress", {}, "Goal progress"),
        ("get_recent_transactions", {"limit": 5}, "Recent transactions"),
        ("get_unusual_transactions", {}, "Unusual transactions"),
        ("get_spending", {"window": "last_week"}, "Spending"),
        ("get_cash_flow", {}, "Income vs spending"),
        ("compare_spending", {"category": "groceries"}, "Spending comparison"),
        ("calculate", {"expression": "2 + 2"}, "Calculated 2 + 2"),
        ("web_search", {"query": "cd rates"}, "Searched “cd rates”"),
        ("propose_goal", {"type": "save", "target_amount": 5000}, "Proposed a savings goal"),
        ("propose_goal", {"type": "save", "name": "Paying off debt", "target_amount": 2000}, "Proposed a savings goal"),
        ("propose_goal", {"type": "save", "name": "Emergency fund", "target_amount": 8000}, "Proposed a savings goal"),
        ("propose_goal", {"type": "track_spending", "category": "Dining"}, "Proposed a spending tracker"),
    ],
)
def test_describe_tool_call(name, tool_input, expected):
    assert _describe_tool_call(name, tool_input) == expected


def test_run_agent_turn_returns_sources_in_call_order(db, user, monkeypatch):
    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(
            turns=[
                ScriptedTurn(
                    final_text="done",
                    tool_calls=[
                        ("get_net_worth", {}),
                        ("get_spending", {"window": "last_week", "category": "eating out"}),
                    ],
                )
            ]
        ),
    )

    monkeypatch.setattr(money_query, "_now", lambda: datetime(2026, 9, 19, 16, tzinfo=timezone.utc))

    reply, sources = run_agent_turn(db, user.id, [{"role": "user", "content": "hi"}])

    assert reply == "done"
    assert sources == [
        {"tool": "get_net_worth", "label": "Net worth"},
        {
            "tool": "get_spending",
            "label": "Dining · Sep 7–13, 2026 · 0 transactions",
            "query": {"start": "2026-09-07", "end": "2026-09-13", "category": "Dining", "merchant": None},
        },
    ]


def test_run_agent_turn_returns_empty_sources_when_no_tool_was_called(db, user, monkeypatch):
    monkeypatch.setattr(claude_agent, "_client", FakeAgentClient(turns=[ScriptedTurn(final_text="hi there")]))

    reply, sources = run_agent_turn(db, user.id, [{"role": "user", "content": "hi"}])

    assert reply == "hi there"
    assert sources == []
