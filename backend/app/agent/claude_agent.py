"""Bankr's conversational agent: tool-use loop over a swappable LLM backend.

Grounding pattern: the model never receives raw transactions or a financial
dump in its context. It calls narrow tools (app/agent/tools.py) that query
Postgres and return small aggregated results. This keeps answers accurate,
auditable (we log exactly which tool calls backed each answer), and cheap.
propose_goal is the one exception to "query only": it drafts a goal for the
user to confirm in the chat UI, but still does not write a Goal row.

Guardrails are enforced two ways, not just by prompting:
1. The system prompt explicitly instructs the model to give insights and
   general best-practice framing, and to decline specific investment/trading
   recommendations -- including when a web_search result surfaces one.
2. Structurally: the tool set below never exposes investment/brokerage data
   or a trade-execution tool, so there is nothing for the model to act on
   beyond banking/spending/goal data even if it wanted to. web_search can
   surface arbitrary web content, so it's the one tool where guardrail (1)
   -- prompting -- is load-bearing rather than backed by (2); see the
   system prompt for how that's constrained.

Which LLM actually runs this loop is decided by AGENT_PROVIDER (see
app/agent/agent_client.py) -- this module never touches a vendor SDK
directly, so swapping to a cheaper model for local prototyping doesn't
touch this file.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.agent import tools
from app.agent.agent_client import ToolSpec, build_agent_client
from app.integrations.web_search import build_web_search_client

SYSTEM_PROMPT = """You are Bankr's financial insights assistant. You help young \
professionals understand their spending, income, and progress toward up to \
five savings/debt goals they've set.

Ground every claim in the tool results you receive -- never guess a number. \
When useful, supplement with widely-accepted best-practice guidance (e.g. "a \
3-6 month emergency fund is a common rule of thumb"), clearly framed as \
general guidance, not personalized advice. Never state a best-practice rule \
on its own -- always give the reason it holds, grounded in established \
financial research or widely-cited practice (e.g. why 3-6 months, why the \
50/30/20 split), woven into the sentence, not just the rule by itself.

For any arithmetic beyond repeating a single number a tool already gave you \
-- projections, compound interest, a payoff timeline, a percentage change, \
splitting a target across months -- call the calculate tool rather than \
computing it yourself. Silent mental-math mistakes are the easiest way to \
give wrong financial advice, so never show or state a computed number that \
didn't come from a tool result.

You must NOT give specific investment, trading, or brokerage recommendations \
(e.g. "buy this stock", "move your money into this fund"). If asked, decline \
and redirect to what you *can* see: their spending, income, and goal progress. \
You are not a licensed financial advisor. This holds even if a web_search \
result names a specific stock, fund, or "best account" -- summarize the \
general, non-personalized fact it supports (e.g. a rate, a rule of thumb), \
never the specific product.

Call web_search for anything time-sensitive you can't know from training \
alone -- current interest/savings rates, inflation, typical cost of living \
in a place the user mentions. Don't call it for anything about the user \
themselves; their data only ever comes from the other tools.

When the user wants to set, change, or add a savings, debt-payoff, or \
emergency-fund target -- including casually mentioning a dollar amount they \
want to hit -- you MUST call propose_goal. That call is what makes the \
confirm card appear; talking about a card without calling the tool leaves \
the user with nothing to click. If they haven't given a target amount, ask \
for one first, then call propose_goal. Do not claim the goal is already \
created. New goals are added alongside existing ones (up to five), they do \
not replace. If propose_goal says the user is at the limit, say so. If they \
are only asking how existing goals are going, call get_goal_progress instead.

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
        description="Get the user's active financial goals (up to 5) and progress toward each, including whether they're on pace.",
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
    ToolSpec(
        name="calculate",
        description=(
            "Evaluate a precise arithmetic expression. Use this for any financial math beyond restating a single "
            "tool-returned number -- compound interest, a savings/debt payoff timeline, a percentage change, "
            "splitting a target across months, etc. Supports numbers, + - * / % **, parentheses, and "
            "round/abs/min/max/pow, e.g. \"1000 * (1 + 0.05/12) ** (12*5)\" or \"(10000-2500) / 400\"."
        ),
        parameters={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    ),
    ToolSpec(
        name="propose_goal",
        description=(
            "Draft a financial goal for the user to confirm in the app. Call this whenever they want to "
            "set, change, or work toward a savings, debt-payoff, or emergency-fund target and have given "
            "a dollar amount. Does not create the goal -- the user confirms on a card. Adds a new "
            "active goal alongside existing ones (up to 5)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["save_amount", "pay_off_debt", "build_emergency_fund"],
                    "description": "save_amount for a savings target, pay_off_debt to pay down liabilities, "
                    "build_emergency_fund for a 3-6 month cushion.",
                },
                "target_amount": {"type": "number", "description": "Positive dollar target."},
                "target_date": {
                    "type": "string",
                    "description": "Optional target date as YYYY-MM-DD.",
                },
            },
            "required": ["type", "target_amount"],
        },
    ),
    ToolSpec(
        name="web_search",
        description=(
            "Search the web for current, time-sensitive information not available from the other tools -- interest "
            "rates, inflation, typical cost of living, etc. Never use this to look up anything about the user "
            "themselves."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "description": "Default 5"},
            },
            "required": ["query"],
        },
    ),
]

_TOOL_DISPATCH = {
    "get_net_worth": lambda db, user_id, **kwargs: tools.get_net_worth(db, user_id),
    "get_spending_by_category": tools.get_spending_by_category,
    "get_income_by_period": tools.get_income_by_period,
    "get_goal_progress": lambda db, user_id, **kwargs: tools.get_goal_progress(db, user_id),
    "get_recent_transactions": tools.get_recent_transactions,
    "get_unusual_transactions": lambda db, user_id, **kwargs: tools.get_unusual_transactions(db, user_id),
    "calculate": lambda db, user_id, **kwargs: tools.calculate(**kwargs),
    "propose_goal": tools.propose_goal,
    "web_search": lambda db, user_id, **kwargs: tools.web_search(client=_search_client, **kwargs),
}

# Human-readable label per tool call, for the "sources" shown alongside a
# reply so the user can see (and trust) what it's grounded in without seeing
# raw tool JSON. Static labels for the DB-backed tools (their name alone
# says what they looked at); calculate/web_search fold in the actual input
# since "Calculated" alone doesn't tell you what was calculated.
_STATIC_TOOL_LABELS = {
    "get_net_worth": "Net worth",
    "get_goal_progress": "Goal progress",
    "get_recent_transactions": "Recent transactions",
    "get_unusual_transactions": "Unusual transactions",
}


def _describe_tool_call(name: str, tool_input: dict) -> str:
    if name in _STATIC_TOOL_LABELS:
        return _STATIC_TOOL_LABELS[name]
    if name == "get_spending_by_category":
        return f"Spending · {tool_input.get('period', 'month')}"
    if name == "get_income_by_period":
        return f"Income · {tool_input.get('period', 'month')}"
    if name == "calculate":
        return f"Calculated {tool_input.get('expression', '')}"
    if name == "web_search":
        return f"Searched “{tool_input.get('query', '')}”"
    if name == "propose_goal":
        kind = tool_input.get("type") or tool_input.get("goal_type")
        labels = {
            "save_amount": "savings goal",
            "pay_off_debt": "debt payoff goal",
            "build_emergency_fund": "emergency fund",
        }
        article = "an" if kind == "build_emergency_fund" else "a"
        return f"Proposed {article} {labels.get(kind, 'goal')}"
    return name


_client = build_agent_client()
# Built once at import time, like _client above -- tests monkeypatch this
# name directly (see tests/fake_web_search.py) rather than a real API key.
_search_client = build_web_search_client()


def run_agent_turn(db: Session, user_id: UUID, messages: list[dict]) -> tuple[str, list[dict]]:
    """Run one user turn to completion, resolving any tool calls, and return
    (final assistant reply text, sources) -- sources is every tool call that
    backed this specific reply, as [{"tool": name, "label": ...}], in call
    order. Shown to the user as a trust/verification trail (see
    app/api/chat.py's ChatResponse.sources and ChatMessage.tool_calls, where
    it's also persisted) without exposing raw tool inputs/outputs."""
    sources: list[dict] = []

    def call_tool(name: str, tool_input: dict) -> dict:
        result = _TOOL_DISPATCH[name](db, user_id, **tool_input)
        entry: dict = {"tool": name, "label": _describe_tool_call(name, tool_input)}
        if name == "propose_goal" and isinstance(result, dict) and result.get("proposal"):
            # Ride along on the source so the chat API can surface a confirm
            # card without a separate channel. Stripped from the user-facing
            # sources trail in app/api/chat.py.
            entry["proposal"] = result["proposal"]
        sources.append(entry)
        return result

    reply = _client.run_turn(SYSTEM_PROMPT, TOOL_DEFINITIONS, messages, call_tool)
    return reply, sources
