"""Bankr's conversational agent: tool-use loop over a swappable LLM backend.

Grounding pattern: the model never receives raw transactions or a financial
dump in its context. It calls narrow, read-only tools (app/agent/tools.py)
that query Postgres and return small aggregated results. This keeps answers
accurate, auditable (we log exactly which tool calls backed each answer),
and cheap.

Guardrails are enforced two ways, not just by prompting:
1. The system prompt explicitly instructs the model to give insights and
   general best-practice framing, and to decline specific investment/trading
   recommendations.
2. Structurally: the tool set below never exposes investment/brokerage data
   or a trade-execution tool, so there is nothing for the model to act on
   beyond banking/spending/goal data even if it wanted to.

Which LLM actually runs this loop is decided by AGENT_PROVIDER (see
app/agent/agent_client.py) -- this module never touches a vendor SDK
directly, so swapping to a cheaper model for local prototyping doesn't
touch this file.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.agent import tools
from app.agent.agent_client import ToolSpec, build_agent_client

SYSTEM_PROMPT = """You are Bankr's financial insights assistant. You help young \
professionals understand their spending, income, and progress toward a single \
savings/debt goal they've set.

Ground every claim in the tool results you receive -- never guess a number. \
When useful, supplement with widely-accepted best-practice guidance (e.g. "a \
3-6 month emergency fund is a common rule of thumb"), clearly framed as \
general guidance, not personalized advice. Never state a best-practice rule \
on its own -- always give the reason it holds, grounded in established \
financial research or widely-cited practice (e.g. why 3-6 months, why the \
50/30/20 split), woven into the sentence, not just the rule by itself.

You must NOT give specific investment, trading, or brokerage recommendations \
(e.g. "buy this stock", "move your money into this fund"). If asked, decline \
and redirect to what you *can* see: their spending, income, and goal progress. \
You are not a licensed financial advisor.

Write in plain conversational prose, 2-4 sentences, like a text message from \
a sharp friend -- never markdown. No headers, no bold/italic asterisks, no \
bullet or numbered lists, no emoji. Lead with the answer, not a preamble \
("Let me check..."). Weave numbers into the sentence itself instead of \
listing them out one per line."""

TOOL_DEFINITIONS = [
    ToolSpec(
        name="get_net_worth",
        description="Get the user's most recent net worth snapshot (total assets, liabilities, net worth).",
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="get_spending_by_category",
        description="Get the user's spending broken down by category for a given period.",
        parameters={
            "type": "object",
            "properties": {"period": {"type": "string", "enum": ["week", "month", "year"]}},
        },
    ),
    ToolSpec(
        name="get_income_by_period",
        description="Get the user's total income for a given period.",
        parameters={
            "type": "object",
            "properties": {"period": {"type": "string", "enum": ["week", "month", "year"]}},
        },
    ),
    ToolSpec(
        name="get_goal_progress",
        description="Get the user's active financial goal and their progress toward it, including whether they're on pace.",
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="get_recent_transactions",
        description="Get the user's most recent transactions.",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max transactions to return, default 20"}},
        },
    ),
    ToolSpec(
        name="get_unusual_transactions",
        description="Get recent transactions that are statistical outliers vs. the user's typical transaction size.",
        parameters={"type": "object", "properties": {}},
    ),
]

_TOOL_DISPATCH = {
    "get_net_worth": lambda db, user_id, **kwargs: tools.get_net_worth(db, user_id),
    "get_spending_by_category": tools.get_spending_by_category,
    "get_income_by_period": tools.get_income_by_period,
    "get_goal_progress": lambda db, user_id, **kwargs: tools.get_goal_progress(db, user_id),
    "get_recent_transactions": tools.get_recent_transactions,
    "get_unusual_transactions": lambda db, user_id, **kwargs: tools.get_unusual_transactions(db, user_id),
}

_client = build_agent_client()


def run_agent_turn(db: Session, user_id: UUID, messages: list[dict]) -> str:
    """Run one user turn to completion, resolving any tool calls, and return
    the final assistant reply text."""

    def call_tool(name: str, tool_input: dict) -> dict:
        return _TOOL_DISPATCH[name](db, user_id, **tool_input)

    return _client.run_turn(SYSTEM_PROMPT, TOOL_DEFINITIONS, messages, call_tool)
