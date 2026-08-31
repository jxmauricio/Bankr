"""Unit coverage for claude_agent's tool-call -> source-label mapping and
run_agent_turn's sources return value, separate from test_chat.py's
HTTP-level coverage."""

import pytest

from app.agent.claude_agent import _describe_tool_call, run_agent_turn
from app.agent import claude_agent
from tests.fake_agent_client import FakeAgentClient, ScriptedTurn


@pytest.mark.parametrize(
    "name,tool_input,expected",
    [
        ("get_net_worth", {}, "Net worth"),
        ("get_goal_progress", {}, "Goal progress"),
        ("get_recent_transactions", {"limit": 5}, "Recent transactions"),
        ("get_unusual_transactions", {}, "Unusual transactions"),
        ("get_spending_by_category", {"period": "year"}, "Spending · year"),
        ("get_spending_by_category", {}, "Spending · month"),
        ("get_income_by_period", {"period": "week"}, "Income · week"),
        ("calculate", {"expression": "2 + 2"}, "Calculated 2 + 2"),
        ("web_search", {"query": "cd rates"}, "Searched “cd rates”"),
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
                        ("get_spending_by_category", {"period": "month"}),
                    ],
                )
            ]
        ),
    )

    reply, sources = run_agent_turn(db, user.id, [{"role": "user", "content": "hi"}])

    assert reply == "done"
    assert sources == [
        {"tool": "get_net_worth", "label": "Net worth"},
        {"tool": "get_spending_by_category", "label": "Spending · month"},
    ]


def test_run_agent_turn_returns_empty_sources_when_no_tool_was_called(db, user, monkeypatch):
    monkeypatch.setattr(claude_agent, "_client", FakeAgentClient(turns=[ScriptedTurn(final_text="hi there")]))

    reply, sources = run_agent_turn(db, user.id, [{"role": "user", "content": "hi"}])

    assert reply == "hi there"
    assert sources == []
