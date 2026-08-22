"""Canned AgentClient stand-in so chat/insight tests don't need a real API
key for any LLM provider -- same role tests/fake_aggregator.py plays for
Plaid. Scripted per-call, not per-vendor, since claude_agent.py and
insights_job.py only ever see the AgentClient Protocol (app/agent/agent_client.py)."""

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ScriptedTurn:
    """One scripted run_turn response. `tool_calls` are invoked against the
    real call_tool closure first -- exercising the real DB-backed tool
    dispatch -- before `final_text` is returned, mimicking a model that
    calls a tool then replies."""

    final_text: str
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)


class FakeAgentClient:
    def __init__(self, turns: list[ScriptedTurn] | None = None, completions: list[str] | None = None):
        self._turns = list(turns or [])
        self._completions = list(completions or [])

    def run_turn(self, system: str, tools: list, history: list[dict], call_tool: Callable[[str, dict], dict]) -> str:
        turn = self._turns.pop(0)
        for name, tool_input in turn.tool_calls:
            call_tool(name, tool_input)
        return turn.final_text

    def complete(self, system: str, user_message: str) -> str:
        return self._completions.pop(0)
