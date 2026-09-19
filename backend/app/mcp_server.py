"""Bankr as an MCP server, so users can connect their own Claude (or any MCP
client) to their Bankr data instead of using the in-app chat agent.

Mounted on the main FastAPI app at POST /mcp (Streamable HTTP, stateless).
Auth is a bearer token minted by POST /auth/mcp-token (see app/auth.py) --
each request resolves to exactly one user, and every tool reads only that
user's rows.

The tool set is a deliberate subset of what the in-app agent gets (see
app/agent/tools.py, which both share): read-only banking/spending/goal data.
Left out on purpose:
- propose_goal: it relies on Bankr's in-app confirm card; a bare MCP client
  has no such step, and an external client shouldn't write goals.
- calculate / web_search: the connecting client already has its own.
As with the in-app agent, there is no investment or trade-execution tool.
"""

import contextlib
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

from app.agent import tools
from app.auth import verify_mcp_token
from app.db import base as db_base

MCP_PATH = "/mcp"

INSTRUCTIONS = (
    "Read-only access to the connected user's Bankr personal-finance data: net worth, "
    "spending, income, savings/debt goals, and transactions. Amounts are USD. Ground every "
    "figure in a tool result. Bankr does not provide investment advice, and neither should you "
    "based on this data."
)

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
]

_current_user_id: ContextVar[UUID] = ContextVar("bankr_mcp_user_id")


@contextmanager
def _session():
    # Looked up at call time (not imported by name) so tests can swap SessionLocal.
    db = db_base.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_mcp_server() -> FastMCP:
    mcp = FastMCP(
        "Bankr",
        instructions=INSTRUCTIONS,
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
        """Income, spending, and the gap between them for a date window (resolved in the user's timezone;
        weeks run Monday-Sunday). start/end (YYYY-MM-DD) override window. Transfers between the user's own
        accounts and credit-card payments count as neither."""
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
    ) -> dict:
        """List individual spending transactions (negative = money out, positive = refund) filtered by
        window, category, merchant substring, and/or charge size. `limit` is capped at 200."""
        with _session() as db:
            return tools.find_transactions(
                db, _current_user_id.get(), window, start, end, category, merchant, min_amount, max_amount,
                max(1, min(limit, 200)),
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

    return mcp


class McpEndpoint:
    """ASGI app for the /mcp path: bearer-token auth in front of the FastMCP app.

    Mounted at "/" on the main app (after all real routes) so that exactly
    /mcp works with no trailing-slash redirect; every other path falls
    through to a plain 404. The inner FastMCP app is created in `lifespan`
    because a FastMCP session manager can only be run once per instance, and
    the main app's lifespan may run several times (e.g. across test clients).
    """

    def __init__(self) -> None:
        self._app: ASGIApp | None = None

    @contextlib.asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        mcp = build_mcp_server()
        self._app = mcp.streamable_http_app()
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            self._app = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].rstrip("/") != MCP_PATH:
            await JSONResponse({"detail": "Not Found"}, status_code=404)(scope, receive, send)
            return

        request = Request(scope)
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        user_id = verify_mcp_token(token.strip()) if scheme.lower() == "bearer" else None
        if user_id is None:
            response = JSONResponse(
                {"detail": "Missing, invalid, or expired MCP token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        if self._app is None:
            await JSONResponse({"detail": "MCP server not running"}, status_code=503)(scope, receive, send)
            return

        # Inner app has its single route at "/", so rewrite the path.
        inner_scope = {**scope, "path": "/", "raw_path": b"/"}
        token_ctx = _current_user_id.set(user_id)
        try:
            await self._app(inner_scope, receive, send)
        finally:
            _current_user_id.reset(token_ctx)
