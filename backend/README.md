# Bankr backend

FastAPI service behind the Bankr web app (`../web`). Holds every secret (Plaid
access tokens, LLM API keys) and is the only thing that talks to Plaid and
the agent's LLM backend — see
`/Users/jxmauricio/.claude/plans/goal-pocket-financial-advisor-ancient-tome.md`
for the full architecture rationale.

**Client note:** the original client was a native iOS app (`../ios`); that's
now shelved in favor of a web app so the product can be tried without any App
Store/simulator friction. The iOS code is untouched and still builds — this
backend doesn't care which client calls it, by design (see the aggregator
note below for why that adapter-boundary habit paid off twice now). Auth
switched from Sign in with Apple to email/password for the web client, since
Sign in with Apple on web requires a verified domain + Apple Developer Services
ID that doesn't exist yet; `/auth/apple` is still here, unused, for whenever
iOS picks back up.

**Aggregator note:** this originally ran on Teller, which shut down its API
in July 2026. It now runs on Plaid. This was a contained swap — one new
adapter file plus `app/api/deps.py` — because every call site depends on the
`BankAggregatorClient` interface in `app/integrations/bank_aggregator.py`,
not on a specific aggregator. If it ever needs to move off Plaid, that's the
same shape of change again.

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values as integrations come online
```

Requires a local Postgres. Quickest path with Homebrew:

```bash
brew install postgresql@16
brew services start postgresql@16
createuser bankr && createdb -O bankr bankr
psql -d postgres -c "ALTER USER bankr WITH PASSWORD 'bankr';"
```

## Run

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

## Test

Tests hit a real local Postgres (`bankr_test`), not sqlite — the schema uses
Postgres-specific types, and aggregator calls are swapped for
`tests/fake_aggregator.py` rather than mocked out entirely.

```bash
createdb -O bankr bankr_test   # once
pytest
```

## Layout

- `app/db/models.py` — SQLAlchemy models (users, linked_accounts, transactions,
  categories, goals, net_worth_snapshots, insight_logs, chat_messages)
- `app/db/migrations/` — Alembic migrations
- `app/db/seed_categories.py` — idempotently seeds Bankr's default categories
- `app/auth.py`, `app/api/auth.py` — `POST /auth/signup` and `POST /auth/login`
  (bcrypt-hashed `password_hash` on `User`) for the web client, plus the
  original `POST /auth/apple` for iOS — all three converge on the same
  `issue_session_token`, so `get_current_user` doesn't care which one ran
- `app/integrations/bank_aggregator.py` — aggregator-agnostic adapter interface
- `app/integrations/plaid_client.py` — Plaid implementation of that interface
- `app/api/deps.py` — `get_aggregator` dependency (swap for a fake in tests via `app.dependency_overrides`)
- `app/services/crypto.py` — Fernet encryption for aggregator access tokens at rest
- `app/services/category_mapper.py` — raw aggregator category → Bankr `Category`
- `app/services/sync_service.py` — pulls accounts+transactions, upserts them, snapshots net worth
- `app/services/goal_service.py` — goal creation + progress recompute (called from sync)
- `app/services/dashboard_service.py` — itemized/rollup queries for the dashboard
- `app/api/accounts.py` — `POST /linked-accounts/link-token` (get a Plaid Link
  token), `POST /linked-accounts` (exchange the resulting public token, sync),
  `POST /linked-accounts/sync` (both sync endpoints also trigger
  `insights_job.run_insights_job` post-sync, best-effort)
- `app/api/dashboard.py` — `GET /dashboard/{net-worth,spending,income,rollup,goal-progress}`
- `app/api/goals.py` — `POST /goals`
- `app/api/chat.py`, `app/services/chat_service.py` — `POST /chat`, persists
  `ChatMessage` history per `conversation_id` around `claude_agent.run_agent_turn`.
  The response also carries `sources` — a human-readable label per tool call
  that backed the reply (e.g. "Net worth", "Searched “high yield savings
  rates”"), shown in the web client as a small caption under the reply so
  the user can see what it's grounded in. Persisted alongside the reply on
  `ChatMessage.tool_calls`, but never fed back into the LLM-facing history —
  see chat_service.py's docstring for why. `GET /chat/conversations` (list,
  newest first, with a preview from the first message) and
  `GET /chat/conversations/{id}` (full history, 404 if it's not this user's)
  let the web client browse and reopen a past conversation — see
  `ChatHistoryMenu.tsx` in the web app
- `app/agent/tools.py` — tool implementations the agent can call. Most are
  DB-backed (also the source of truth `dashboard_service.py` and
  `goal_service.py` reuse for net worth and goal pacing, so the dashboard and
  chat agent never disagree). Two aren't: `calculate` (a precise
  AST-whitelisted arithmetic evaluator, so financial projections don't rely
  on LLM mental math) and `web_search` (current rates/inflation/etc. via
  `app/integrations/web_search.py`, gracefully unconfigured without
  `BRAVE_SEARCH_API_KEY`)
- `app/agent/agent_client.py` — vendor-agnostic `AgentClient` Protocol (`run_turn`
  for the tool-use loop, `complete` for one-shot phrasing) + `build_agent_client()`,
  selected by `AGENT_PROVIDER` (`openrouter` | `anthropic` | `openai_compatible`).
  Same adapter-boundary pattern as `BankAggregatorClient` — `claude_agent.py`
  and `insights_job.py` never touch a vendor SDK directly, so swapping the LLM
  is a config change.
- `app/agent/providers.py` — the three `AgentClient` implementations:
  `OpenRouterAgentClient` (default — routes to `OPENROUTER_MODEL` via
  openrouter.ai, sends OpenRouter's recommended attribution headers),
  `AnthropicAgentClient` (Claude's native Messages API), and the generic
  `OpenAICompatibleAgentClient` (any other `/chat/completions`-shaped API —
  DeepSeek, Kimi/Moonshot, GPT-5-mini, ... directly). `OpenRouterAgentClient`
  is a thin subclass of the generic client; each keeps its own
  vendor-specific message-threading entirely internal. `AGENT_EXTENDED_THINKING`
  turns on reasoning before the reply for the two providers where it's wired
  up (Claude's native `thinking` param on `AnthropicAgentClient`, OpenRouter's
  unified `reasoning` param on `OpenRouterAgentClient` — a no-op there unless
  `OPENROUTER_MODEL` itself supports reasoning)
- `app/agent/claude_agent.py` — the tool-use loop itself: tool schema
  (`TOOL_DEFINITIONS`), guardrailed system prompt, dispatch to `tools.py`,
  `run_agent_turn(db, user_id, history) -> (reply, sources)`. Despite the
  filename this runs against whichever provider `AGENT_PROVIDER` selects,
  not only Claude (kept the name since Claude is still the production
  default)
- `app/jobs/insights_job.py` — post-sync proactive insight detection + LLM phrasing
  (via the same `AgentClient.complete`)
- `app/main.py` — also sets up `CORSMiddleware` for the web app's dev origin
  (`http://localhost:5173`); tighten `allow_origins` once the web app has a
  real deployed origin

`/chat` and `insights_job` are structurally verified against a fake
`AgentClient` (`tests/fake_agent_client.py`, same pattern as the fake
aggregator) — that test suite is what caught and fixed a real bug where a
brand-new goal would instantly look "behind pace" (see `get_goal_progress`
in `app/agent/tools.py`). Neither has been exercised against a real LLM API
yet.

## Agent provider

`AGENT_PROVIDER=openrouter` (the default) routes the tool-use loop through
[OpenRouter](https://openrouter.ai) via `OPENROUTER_API_KEY`/
`OPENROUTER_MODEL`. Default model is `deepseek/deepseek-v4-flash-0731`
(DeepSeek V4 Flash, GA as of July 2026) — cheap (~$0.065/$0.18 per million
input/output tokens), supports tool calling, and a solo dev doesn't need a
separate DeepSeek account: one OpenRouter key covers this model and gives an
easy escape hatch to swap in any other OpenRouter-hosted model (including
Claude) later by changing `OPENROUTER_MODEL` alone, no code or key changes.
`OPENROUTER_SITE_URL`/`OPENROUTER_APP_NAME` set OpenRouter's recommended
attribution headers (optional, but they're what make usage show up
correctly attributed in OpenRouter's own dashboard).

Two other providers remain available, no code changes needed — just flip
`AGENT_PROVIDER`:

- `anthropic` — Claude's native Messages API directly, via
  `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL`. Worth it if you want to validate
  final prompt/guardrail behavior against Claude specifically rather than
  through a router.
- `openai_compatible` — points at any other `/chat/completions`-shaped
  endpoint directly (DeepSeek's own API, Kimi/Moonshot, GPT-5-mini, ...) via
  `AGENT_API_KEY`/`AGENT_MODEL`/`AGENT_BASE_URL`, bypassing OpenRouter
  entirely if you'd rather hold vendor keys yourself.

## Not yet wired up

1. A real `OPENROUTER_API_KEY` (or a key for one of the other two providers
   above) to exercise `claude_agent.py` and `insights_job.py` against a live
   LLM (currently mock-verified only — `/chat` degrades to a clear in-UI
   error without one, verified live in the web app).
2. `app/integrations/apns.py` for push delivery of insights (currently
   `InsightLog.delivered_via` is always `"in_app"`) — was iOS-specific to
   begin with and is lower priority now that iOS is shelved; the web app has
   no push story yet either.
3. A periodic/webhook-driven sync trigger — today sync only happens when the
   client calls `/linked-accounts` or `/linked-accounts/sync`. Plaid webhook
   signature verification (`PlaidClient.verify_webhook_signature`) is also
   still a stub — Plaid signs webhooks with a JWT, not a simple HMAC.

Real Plaid credentials **are** wired up and verified end-to-end against the
live Sandbox API (see `../ios/README.md` for the original verification
narrative — same backend code, so it applies here unchanged). The Plaid Link
step itself couldn't be click-tested by browser automation in the web app
(Plaid's hosted Link UI runs in a cross-origin iframe hardened against
scripted interaction), so the web app's post-link pipeline — sync, dashboard,
goal pacing, chat — was instead verified by seeding a user through
`sync_user_accounts` with `tests/fake_aggregator.py` and a real session JWT,
the same DB-level path a real Plaid Link completion produces.
