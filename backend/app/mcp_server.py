"""Bankr as an MCP server, so users can connect their own Claude (or any MCP
client) to their Bankr data instead of using the in-app chat agent.

Mounted on the main FastAPI app at POST /mcp (Streamable HTTP, stateless).
Auth is an OAuth 2.1 access token (app/mcp_oauth.py: how Claude and ChatGPT
custom connectors connect) or the legacy token minted by POST
/auth/mcp-token (app/auth.py). Each request resolves to exactly one user,
and every tool reads only that user's rows.

Two scopes:
- read: a deliberate subset of what the in-app agent gets (see
  app/agent/tools.py, which both share): banking/spending/goal data.
- write (read + write): also the propose_* tools. They never change
  anything: each stores a pending proposal (app/services/proposal_service.py)
  that the user has to confirm in Bankr, just as the in-app agent's
  proposals wait for a tap on a confirm card.
Left out on purpose: calculate / web_search (the connecting client already
has its own). As with the in-app agent, there is no investment or
trade-execution tool.
"""

import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app import mcp_oauth
from app.agent import tools
from app.db import base as db_base
from app.mcp_oauth import MCP_PATH, READ, WRITE, McpCaller
from app.services import proposal_service

INSTRUCTIONS = (
    "Access to the connected user's Bankr personal-finance data: net worth, "
    "spending, income, savings/debt goals, and transactions. Amounts are USD. Ground every "
    "figure in a tool result. Bankr does not provide investment advice, and neither should you "
    "based on this data."
)
WRITE_INSTRUCTIONS = (
    " The propose_* tools never change anything themselves: each saves a proposal the user must "
    "confirm in the Bankr app. After calling one, tell the user it's waiting for them in Bankr; "
    "never say the change is made."
)

WRITE_TOOLS = {"propose_goal", "propose_rule", "propose_budget_move", "propose_recategorization"}

Window = Literal[
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "this_year",
    "last_year",
    "last_7_days",
    "last_30_days",
    "last_90_days",
    "last_3_months",
]

_current_user_id: ContextVar[UUID] = ContextVar("bankr_mcp_user_id")
_current_caller: ContextVar[McpCaller] = ContextVar("bankr_mcp_caller")


@contextmanager
def _session():
    # Looked up at call time (not imported by name) so tests can swap SessionLocal.
    db = db_base.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _propose(kind: str, draft: dict, payload: dict | None = None) -> dict:
    """Store a validated draft as a pending proposal; pass errors through."""
    if draft.get("status") != "proposed":
        return draft
    caller = _current_caller.get()
    with _session() as db:
        return proposal_service.save(
            db, caller.user_id, kind, payload or draft["action"], caller.grant_id, caller.client_name
        )


def build_mcp_server(write: bool = False) -> FastMCP:
    mcp = FastMCP(
        "Bankr",
        instructions=INSTRUCTIONS + (WRITE_INSTRUCTIONS if write else ""),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        # DNS-rebinding protection guards cookie-authed localhost servers; this
        # endpoint is bearer-token authed and meant to be reached by hostname.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.tool()
    def get_net_worth() -> dict:
        """Get the user's net worth: total assets, liabilities, and the balance of every linked account."""
        with _session() as db:
            return tools.get_net_worth(db, _current_user_id.get())

    @mcp.tool()
    def get_cash_flow(window: Window = "this_month", start: str | None = None, end: str | None = None) -> dict:
        """Income, spending, and transfers that leave or enter the linked accounts (brokerage sends,
        Venmo, ATM) for a date window. net is income − spending + transfer_in − transfer_out.
        Credit-card payoffs and checking↔savings count as neither."""
        with _session() as db:
            return tools.get_cash_flow(db, _current_user_id.get(), window, start, end)

    @mcp.tool()
    def get_spending(
        window: Window = "this_month",
        start: str | None = None,
        end: str | None = None,
        category: str | None = None,
        group_by: Literal["category", "subcategory", "merchant"] | None = None,
        top_n: int | None = None,
    ) -> dict:
        """How much the user spent in a date window, optionally for one category (e.g. Groceries, Dining,
        Gas -- everyday words like "eating out" work too), optionally broken down by category, subcategory,
        or merchant. Totals are net of refunds; pending charges are included and reported separately."""
        with _session() as db:
            return tools.get_spending(db, _current_user_id.get(), window, start, end, category, group_by, top_n)

    @mcp.tool()
    def compare_spending(
        category: str | None = None,
        current_window: Window = "this_month",
        previous_window: Window | None = None,
    ) -> dict:
        """Compare spending between two windows (default: this month vs last month), optionally for one
        category. Includes the exact difference and percent change, and for an in-progress period also the
        previous period cut off at the same point for a like-for-like comparison."""
        with _session() as db:
            return tools.compare_spending(
                db, _current_user_id.get(), current_window, previous_window, category
            )

    @mcp.tool()
    def find_transactions(
        window: Window = "this_month",
        start: str | None = None,
        end: str | None = None,
        category: str | None = None,
        merchant: str | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        limit: int = 50,
        kind: Literal["spending", "income", "transfer", "all"] | None = None,
    ) -> dict:
        """List individual transactions (negative = money out, positive = money in) filtered by
        window, category, merchant substring, and/or charge size. Default is spending; a merchant
        lookup with no kind also searches transfers (Fidelity, Venmo, card payoffs). `limit` is
        capped at 200."""
        with _session() as db:
            return tools.find_transactions(
                db, _current_user_id.get(), window, start, end, category, merchant, min_amount, max_amount,
                max(1, min(limit, 200)), kind,
            )

    @mcp.tool()
    def get_goal_progress() -> dict:
        """Get the user's active financial goals (up to 5) and progress toward each, including whether they're on pace."""
        with _session() as db:
            return tools.get_goal_progress(db, _current_user_id.get())

    @mcp.tool()
    def get_recent_transactions(limit: int = 20) -> dict:
        """Get the user's most recent transactions (negative amounts are money out). `limit` is capped at 100."""
        with _session() as db:
            return tools.get_recent_transactions(db, _current_user_id.get(), max(1, min(limit, 100)))

    @mcp.tool()
    def get_unusual_transactions() -> dict:
        """Get recent transactions that are statistical outliers vs. the user's typical transaction size."""
        with _session() as db:
            return tools.get_unusual_transactions(db, _current_user_id.get())

    if write:
        _add_write_tools(mcp)
    return mcp


def _add_write_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def propose_goal(
        type: Literal["save", "track_spending"],
        target_amount: float | None = None,
        target_date: str | None = None,
        name: str | None = None,
        category: str | None = None,
        window: Literal["this_week", "this_month", "this_year", "last_7_days", "last_30_days", "last_90_days"] | None = None,
    ) -> dict:
        """Propose a goal for the user to confirm in Bankr: "save" toward target_amount (optional
        target_date YYYY-MM-DD and a name like "Emergency fund"), or "track_spending" in a category
        (optional cap as target_amount). Changes nothing until the user confirms in the Bankr app."""
        with _session() as db:
            draft = tools.propose_goal(
                db, _current_user_id.get(), type=type, target_amount=target_amount, target_date=target_date,
                name=name, category=category, window=window,
            )
        if draft.get("status") != "proposed":
            return draft
        fields = ("type", "name", "target_amount", "target_date", "category", "window")
        return _propose("goal", draft, {k: draft["proposal"].get(k) for k in fields})

    @mcp.tool()
    def propose_rule(merchant: str, category: str, rename_to: str | None = None) -> dict:
        """Propose a rule "always put transactions whose merchant contains <merchant> in <category>"
        (optionally renaming the merchant), also applied to past transactions. Changes nothing until
        the user confirms in the Bankr app."""
        with _session() as db:
            draft = tools.propose_rule(db, _current_user_id.get(), merchant, category, rename_to)
        return _propose("rule", draft)

    @mcp.tool()
    def propose_budget_move(from_line: str, to_line: str, amount: float, month: str | None = None) -> dict:
        """Propose moving budget money between two lines (a category, or "Flexible") for a month
        (YYYY-MM, default this month), e.g. to cover overspending. Changes nothing until the user
        confirms in the Bankr app."""
        with _session() as db:
            draft = tools.propose_budget_move(db, _current_user_id.get(), from_line, to_line, amount, month)
        return _propose("budget_move", draft)

    @mcp.tool()
    def propose_recategorization(transaction_id: str, category: str) -> dict:
        """Propose putting one transaction (its id from find_transactions) in another category.
        Changes nothing until the user confirms in the Bankr app."""
        with _session() as db:
            draft = proposal_service.draft_recategorization(db, _current_user_id.get(), transaction_id, category)
        return _propose("recategorize", draft)


def _challenge(request: Request, status_code: int, detail: str, **params: str) -> JSONResponse:
    """RFC 6750 / RFC 9728 challenge: where to find the authorization server
    and which scopes to ask for."""
    fields = {**params, "scope": f"{READ} {WRITE}" if status_code == 401 else WRITE}
    fields["resource_metadata"] = mcp_oauth.resource_metadata_url(request)
    header = "Bearer " + ", ".join(f'{k}="{v}"' for k, v in fields.items())
    return JSONResponse({"detail": detail}, status_code=status_code, headers={"WWW-Authenticate": header})


def _calls_write_tool(body: bytes) -> bool:
    try:
        messages = json.loads(body)
    except ValueError:
        return False
    for m in messages if isinstance(messages, list) else [messages]:
        if isinstance(m, dict) and m.get("method") == "tools/call":
            if (m.get("params") or {}).get("name") in WRITE_TOOLS:
                return True
    return False


class McpEndpoint:
    """ASGI app for the /mcp path: token auth in front of two FastMCP apps,
    one per scope, so a read-only connection doesn't even list the write
    tools.

    Mounted at "/" on the main app (after all real routes) so that exactly
    /mcp works with no trailing-slash redirect; every other path falls
    through to a plain 404. The inner FastMCP apps are created in `lifespan`
    because a FastMCP session manager can only be run once per instance, and
    the main app's lifespan may run several times (e.g. across test clients).
    """

    def __init__(self) -> None:
        self._apps: dict[bool, ASGIApp] = {}

    @contextlib.asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        read_server, write_server = build_mcp_server(), build_mcp_server(write=True)
        apps = {False: read_server.streamable_http_app(), True: write_server.streamable_http_app()}
        try:
            async with read_server.session_manager.run(), write_server.session_manager.run():
                self._apps = apps
                yield
        finally:
            self._apps = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].rstrip("/") != MCP_PATH:
            await JSONResponse({"detail": "Not Found"}, status_code=404)(scope, receive, send)
            return

        request = Request(scope)
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        caller = None
        if scheme.lower() == "bearer" and token.strip():
            with _session() as db:
                caller = mcp_oauth.authenticate_mcp(db, token.strip(), mcp_oauth.resource_url(request))
        if caller is None:
            response = _challenge(request, 401, "Missing, invalid, expired, or revoked token")
            await response(scope, receive, send)
            return

        if not self._apps:
            await JSONResponse({"detail": "MCP server not running"}, status_code=503)(scope, receive, send)
            return

        can_write = WRITE in caller.scopes
        if not can_write and scope["method"] == "POST":
            # Read the body to spot a write tool called with a read-only
            # token, then replay it to the inner app.
            body, more = b"", True
            while more:
                message = await receive()
                body += message.get("body", b"")
                more = message.get("more_body", False)
            if _calls_write_tool(body):
                response = _challenge(
                    request, 403, "This connection is read-only. Reconnect Bankr with read + write to propose changes.",
                    error="insufficient_scope",
                )
                await response(scope, receive, send)
                return
            replayed = False

            async def receive() -> dict:  # noqa: F811 -- replaces the consumed one
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}

        # Inner app has its single route at "/", so rewrite the path.
        inner_scope = {**scope, "path": "/", "raw_path": b"/"}
        user_ctx = _current_user_id.set(caller.user_id)
        caller_ctx = _current_caller.set(caller)
        try:
            await self._apps[can_write](inner_scope, receive, send)
        finally:
            _current_caller.reset(caller_ctx)
            _current_user_id.reset(user_ctx)
