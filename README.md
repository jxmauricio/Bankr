# Bankr

An AI-first personal finance app: link your bank accounts, track net worth,
set a goal, and ask a chat agent about your money instead of digging through
tabs. Full architecture rationale lives in
`/Users/jxmauricio/.claude/plans/goal-pocket-financial-advisor-ancient-tome.md`.

## Repo layout

| Path       | What it is                                                                 |
| ---------- | --------------------------------------------------------------------------- |
| `backend/` | FastAPI service — the only thing that talks to Plaid and the LLM. Holds every secret. |
| `web/`     | React + Vite app, the primary client (see `web/README.md`).                |
| `ios/`     | SwiftUI app, shelved in favor of `web/` but still builds (see `ios/README.md`). |
| `design/`  | Static design spec / style reference.                                      |

Each subproject has its own README with full setup/run/layout detail — this
file is the entry point: how to get everything running locally, and what
tokens you need to do it.

## Quick start

You need the backend running first — both clients call `http://localhost:8000`.

```bash
# 1. Backend
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in tokens, see below
# local Postgres, if you don't already have one:
brew install postgresql@16 && brew services start postgresql@16
createuser bankr && createdb -O bankr bankr
psql -d postgres -c "ALTER USER bankr WITH PASSWORD 'bankr';"
alembic upgrade head
uvicorn app.main:app --reload    # http://localhost:8000

# 2. Web client (in a second terminal)
cd web
npm install
npm run dev                      # http://localhost:5173
```

Open `http://localhost:5173`, sign up with any email/password, and go
through onboarding. See `backend/README.md` and `web/README.md` for testing,
full file layout, and what's not wired up yet.

## Tokens developers need

Everything below is a `backend/.env` value (copy `backend/.env.example` to
start) — the web and iOS clients hold no secrets themselves, they only ever
talk to the backend.

### Required to run at all

| Variable               | What it's for                                            | How to get it |
| ----------------------- | ---------------------------------------------------------- | -------------- |
| `DATABASE_URL`          | Postgres connection string.                                | Local Postgres (see Quick start) works out of the box with the default value. A shared Supabase instance also works — see the comment block above it in `.env.example` for the exact pooler URL to use (session pooler, not direct/transaction). |
| `SESSION_JWT_SECRET`    | Signs the backend-issued session JWT.                      | Any random string for local dev; a real secret in production. |
| `TOKEN_ENCRYPTION_KEY`  | Fernet key encrypting Plaid access tokens at rest.          | Generate one: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

The app boots and you can sign up/sign in with just these three set — bank
linking and the chat agent will error gracefully (not crash) until you add
the tokens below.

### Required for bank linking (Plaid)

| Variable          | What it's for                        | How to get it |
| ------------------ | --------------------------------------- | -------------- |
| `PLAID_CLIENT_ID`  | Identifies your app to Plaid.           | [Plaid Dashboard](https://dashboard.plaid.com) → Team Settings → Keys (free to sign up, Sandbox is free). |
| `PLAID_SECRET`     | Paired with the client ID.              | Same page — use the **Sandbox** secret for local dev. |
| `PLAID_ENV`        | Which Plaid environment to hit.         | `sandbox` for local dev (test institutions, fake logins like `user_good`/`pass_good`). |
| `PLAID_WEBHOOK_SECRET` | Verifies Plaid webhook signatures.  | Not yet wired up (see `backend/README.md`) — leave blank for local dev. |

Without these, sign-up/sign-in/dashboard/goals all still work; only the
"link a bank" step fails.

### Required for the chat agent (pick one provider)

Set `AGENT_PROVIDER` to one of the three below, then fill in that provider's
variables. Without any of these, `/chat` returns a clear in-UI error instead
of crashing.

| `AGENT_PROVIDER` | Variables                                              | How to get it |
| ------------------ | -------------------------------------------------------- | -------------- |
| `openrouter` (default) | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`          | [openrouter.ai](https://openrouter.ai) — one key covers many models, including the default `deepseek/deepseek-v4-flash-0731`. Cheapest option for local dev. |
| `anthropic`         | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`                  | [console.anthropic.com](https://console.anthropic.com) — use this if you want to test against Claude specifically, not through a router. |
| `openai_compatible` | `AGENT_API_KEY`, `AGENT_MODEL`, `AGENT_BASE_URL`        | Any `/chat/completions`-shaped API you already hold a key for (DeepSeek's own API, Kimi/Moonshot, etc.). |

### iOS-only (skip these if you're only running the web client)

| Variable | What it's for |
| ---------- | ---------------- |
| `APPLE_TEAM_ID`, `APPLE_CLIENT_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY_PATH` | Sign in with Apple — only used by `POST /auth/apple` for the iOS client. The web client uses email/password instead. |
| `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_AUTH_KEY_PATH`, `APNS_TOPIC`, `APNS_USE_SANDBOX` | Push notifications — not yet wired up on either client (see `backend/README.md`). |

## Full documentation

- [`backend/README.md`](backend/README.md) — setup, running tests, full
  service layout, agent provider details, what's not yet wired up.
- [`web/README.md`](web/README.md) — stack, auth, page/component layout,
  what's been verified end-to-end.
- [`ios/README.md`](ios/README.md) — XcodeGen setup, dependencies, layout,
  what's been verified end-to-end.
