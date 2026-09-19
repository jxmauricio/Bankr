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
from app.db.seed_categories import DEFAULT_CATEGORIES
from app.integrations.web_search import build_web_search_client
from app.services import money_query as mq

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

Money answers must be exact and checkable, because the user should never \
need to open their bank's app to verify one:
- Never work out dates yourself. Pass a named window (this_month, \
last_month, last_week, ...) or explicit start/end dates to the tool, and \
state the resolved dates it returns in your answer ("Sep 7–13"), so the \
user knows exactly what period the number covers.
- Pick the most specific category that matches what they said. Gas for the \
car is "Gas", not "Transportation" and never "Utilities". Eating out is \
"Dining". For "what am I spending on", use get_spending with \
group_by="category".
- For "this month vs last month", use compare_spending. When the result \
includes previous_to_same_point, the current month isn't over yet: lead \
with that like-for-like comparison and mention the full last month too.
- If transaction_count is 0, say you found no transactions in that window \
rather than implying they spent nothing. If pending_amount is non-zero, \
say how much of the total is still pending. If refunds are non-zero, \
mention that the total is net of them.
- If a tool returns an error with did_you_mean or valid options, retry with \
one of those instead of giving up or guessing.

Write in plain conversational prose, 2-4 sentences, like a text message from \
a sharp friend -- never markdown. No headers, no bold/italic asterisks, no \
bullet or numbered lists, no emoji. Lead with the answer, not a preamble \
("Let me check..."). Weave numbers into the sentence itself instead of \
listing them out one per line."""

_SPEND_CATEGORIES = ", ".join(name for name, type_, _ in DEFAULT_CATEGORIES if type_ == "expense")
_WINDOW_PROPS = {
    "window": {
        "type": "string",
        "enum": list(mq.NAMED_WINDOWS),
        "description": "Named date window, resolved in the user's timezone. Weeks run Monday-Sunday. "
        "Default this_month.",
    },
    "start": {"type": "string", "description": "Explicit start date YYYY-MM-DD (overrides window)."},
    "end": {"type": "string", "description": "Explicit end date YYYY-MM-DD, inclusive. Defaults to today."},
}
_CATEGORY_PROP = {
    "type": "string",
    "description": f"Spending category: one of {_SPEND_CATEGORIES}. Everyday words also work "
    "(\"eating out\", \"fuel\"). A parent category includes its subcategories (Dining includes Coffee). "
    "Omit for all spending.",
}

TOOL_DEFINITIONS = [
    ToolSpec(
        name="get_net_worth",
        description="Get the user's net worth right now: total assets, total liabilities, and the balance of "
        "every linked account that makes it up.",
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="get_cash_flow",
        description="Income, spending, and the gap between them (net) for a date window. Transfers between "
        "the user's own accounts and credit-card payments count as neither.",
        parameters={"type": "object", "properties": _WINDOW_PROPS},
    ),
    ToolSpec(
        name="get_spending",
        description="How much the user spent in a date window, optionally for one category, optionally broken "
        "down by category, subcategory, or merchant. Totals are net of refunds and include pending charges "
        "(reported separately).",
        parameters={
            "type": "object",
            "properties": {
                **_WINDOW_PROPS,
                "category": _CATEGORY_PROP,
                "group_by": {"type": "string", "enum": ["category", "subcategory", "merchant"]},
                "top_n": {"type": "integer", "description": "With group_by: keep the N biggest groups, roll up the rest."},
            },
        },
    ),
    ToolSpec(
        name="compare_spending",
        description="Compare spending between two date windows, optionally for one category, e.g. groceries "
        "this month vs last month. Returns both totals plus the exact difference and percent change.",
        parameters={
            "type": "object",
            "properties": {
                "category": _CATEGORY_PROP,
                "current_window": {"type": "string", "enum": list(mq.NAMED_WINDOWS), "description": "Default this_month."},
                "previous_window": {
                    "type": "string",
                    "enum": list(mq.NAMED_WINDOWS),
                    "description": "Defaults to the period before current_window (this_month -> last_month).",
                },
                "current_start": {"type": "string"},
                "current_end": {"type": "string"},
                "previous_start": {"type": "string"},
                "previous_end": {"type": "string"},
            },
        },
    ),
    ToolSpec(
        name="find_transactions",
        description="List the individual spending transactions behind a figure (negative = money out, "
        "positive = refund), filtered by window, category, merchant name, and/or charge size.",
        parameters={
            "type": "object",
            "properties": {
                **_WINDOW_PROPS,
                "category": _CATEGORY_PROP,
                "merchant": {"type": "string", "description": "Case-insensitive substring of the merchant name."},
                "min_amount": {"type": "number", "description": "Minimum charge size in dollars."},
                "max_amount": {"type": "number", "description": "Maximum charge size in dollars."},
                "limit": {"type": "integer", "description": "Default 50."},
            },
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
    "get_cash_flow": tools.get_cash_flow,
    "get_spending": tools.get_spending,
    "compare_spending": tools.compare_spending,
    "find_transactions": tools.find_transactions,
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
    "get_goal_progress": "Goal progress",
    "get_recent_transactions": "Recent transactions",
    "get_unusual_transactions": "Unusual transactions",
}


def _count(n: int) -> str:
    return f"{n} transaction{'' if n == 1 else 's'}"


def _describe_tool_call(name: str, tool_input: dict, result: dict | None = None) -> str:
    """Labels for money tools are built from the *result* -- the resolved
    dates and transaction count -- so the chip under a reply says exactly
    what the number covers ("Dining · Sep 7–13, 2026 · 5 transactions")."""
    result = result if isinstance(result, dict) and "error" not in result else None
    if name in _STATIC_TOOL_LABELS:
        return _STATIC_TOOL_LABELS[name]
    if name == "get_net_worth":
        if result and result.get("accounts") is not None:
            n = len(result["accounts"])
            return f"Net worth · {n} account{'' if n == 1 else 's'}"
        return "Net worth"
    if name in ("get_spending", "find_transactions"):
        what = (result or {}).get("category") or tool_input.get("category")
        what = what or ("Transactions" if name == "find_transactions" else "Spending")
        if name == "find_transactions" and tool_input.get("merchant"):
            what = f"{what} · “{tool_input['merchant']}”"
        if result is None:
            return what
        return f"{what} · {result['label']} · {_count(result['transaction_count'])}"
    if name == "get_cash_flow":
        return f"Income vs spending · {result['label']}" if result else "Income vs spending"
    if name == "compare_spending":
        what = (result or {}).get("category") or "Spending"
        if result is None:
            return f"{what} comparison"
        previous = result.get("previous_to_same_point") or result["previous"]
        return f"{what} · {result['current']['label']} vs {previous['label']}"
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


def _source_query(name: str, tool_input: dict, result: dict) -> dict | None:
    """The transaction filter a source chip opens, so the user can see the
    exact rows behind a number. Only for tools whose figure is a sum of
    spending transactions."""
    if not isinstance(result, dict) or "error" in result:
        return None
    if name == "compare_spending":
        result = result["current"]
    elif name not in ("get_spending", "find_transactions"):
        return None
    return {
        "start": result["start"],
        "end": result["end"],
        "category": result.get("category"),
        "merchant": tool_input.get("merchant") if name == "find_transactions" else None,
    }


def _date_context(db: Session, user_id: UUID) -> str:
    today = mq.today_for_user(db, user_id)
    return f"\n\nToday is {today:%A}, {today:%B} {today.day}, {today.year} in the user's timezone."


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
        entry: dict = {"tool": name, "label": _describe_tool_call(name, tool_input, result)}
        query = _source_query(name, tool_input, result)
        if query:
            entry["query"] = query
        if name == "propose_goal" and isinstance(result, dict) and result.get("proposal"):
            # Ride along on the source so the chat API can surface a confirm
            # card without a separate channel. Stripped from the user-facing
            # sources trail in app/api/chat.py.
            entry["proposal"] = result["proposal"]
        sources.append(entry)
        return result

    system = SYSTEM_PROMPT + _date_context(db, user_id)
    reply = _client.run_turn(system, TOOL_DEFINITIONS, messages, call_tool)
    return reply, sources
