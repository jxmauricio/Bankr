# Bankr web

React + TypeScript app (Vite), the primary Bankr client — see `../ios` for
the original native app, now shelved (see `../backend/README.md` for why).

## Stack

- **Vite + React + TypeScript**
- **Tailwind CSS v4** (CSS-first config via `@theme` in `src/index.css` — no
  `tailwind.config.js`). Fonts: Space Grotesk (display), IBM Plex Sans (body),
  IBM Plex Mono (all monetary/tabular figures — a deliberate signature, not
  an accident: money should always read as exact, not prose).
- **react-plaid-link 5.0.0** for the Plaid Link web flow. API verified
  against the installed package's own `.d.ts` files, not guessed:
  `usePlaidLink({ token, onSuccess, onExit })` → `{ open, ready }`.
- **react-router-dom** installed but not yet used — the onboarding gate in
  `App.tsx` currently does step-based conditional rendering instead of real
  routes, matching the iOS app's `RootView`/`PostSignInGateView` shape. Worth
  revisiting if deep-linking (e.g. a shareable dashboard URL) becomes a goal.

## Auth

Email + password, not Sign in with Apple — see `../backend/README.md` for
why. Session token is a backend-issued JWT kept in `localStorage`
(`src/lib/session.tsx`); acceptable for an MVP but worth moving to an
httpOnly cookie before this ever handles a real user's real bank data (XSS
would leak a `localStorage` token; a cookie set httpOnly wouldn't be
readable by injected script).

## Layout

- `src/lib/api.ts` — the only thing that talks to the backend; mirrors every
  endpoint in `../backend/app/api/`
- `src/lib/session.tsx` — session token context, backed by `localStorage`
- `src/lib/format.ts` — money/date formatting, goal type labels
- `src/App.tsx` — signed-out → `AuthPage`; signed-in → onboarding gate that
  routes through `LinkBankPage` → `GoalSetupPage` → `DashboardPage` based on
  `GET /dashboard/net-worth` and `GET /dashboard/goal-progress`, same logic
  as the iOS app's `PostSignInGateView`
- `src/pages/AuthPage.tsx` — combined sign up / sign in
- `src/pages/LinkBankPage.tsx` — fetches a link token from
  `POST /linked-accounts/link-token`, launches Plaid Link, posts the
  resulting `public_token` to `POST /linked-accounts` on success
- `src/pages/GoalSetupPage.tsx` — goal type + target amount/date, posts to
  `POST /goals`
- `src/pages/DashboardPage.tsx` — net worth, goal pace, week/month/year
  rollup, itemized spending/income
- `src/components/GoalPaceTrack.tsx` — the dashboard's signature element: a
  single track plotting both actual progress (solid fill) and the pace
  needed to hit the target date (a marker), so ahead/behind is visible at a
  glance instead of buried in a percentage
- `src/components/ChatPanel.tsx` — slide-over chat reachable from a
  persistent floating "Ask Bankr" button on the dashboard (AI-agent-first,
  not a buried tab), posts to `POST /chat`

## Run

```bash
npm install
npm run dev      # http://localhost:5173
```

The backend must be running locally (`cd ../backend && uvicorn app.main:app --reload`)
with `CORSMiddleware` allowing `http://localhost:5173` (already configured in
`app/main.py`) — `src/lib/api.ts`'s `BASE_URL` points at `http://localhost:8000`.

## Verified

Full loop tested live in-browser: sign up → CORS-permitted request lands →
`LinkBankPage` fetches a real link token → Plaid Link renders the real
Sandbox UI (institution picker, phone-number step) with a real link token.
**The Plaid Link click-through itself could not be automated** — Plaid's
hosted Link UI runs in a cross-origin iframe that doesn't respond to
synthetic input events (anti-fraud hardening, not a Bankr bug; confirmed via
`document.elementFromPoint` — clicks land on the iframe element but never
reach its internal content, even for its own close button). If you click
through it yourself with `user_good`/`pass_good` it'll work exactly like the
verified iOS flow, since it's the same backend endpoints underneath.

To verify everything downstream of that one step, a user was seeded directly
through `sync_user_accounts` with `tests/fake_aggregator.py` (the same code
path a real Plaid Link completion drives) plus a real session JWT injected
into `localStorage`. That confirmed: onboarding gate routing, `DashboardPage`
(net worth, goal pace track, week/month/year rollup toggle, spending/income
tab toggle, itemized transaction list), `ChatPanel` (correctly shows a
graceful error — no `OPENROUTER_API_KEY` configured yet, same as iOS), sign
out, and signing back in with the same credentials. Also checked at the
mobile viewport (375×812) — layout reflows cleanly, no overlap.

## Not yet wired up

1. A real `OPENROUTER_API_KEY` on the backend — see `../backend/README.md`.
2. Moving the session token from `localStorage` to an httpOnly cookie (see
   Auth above).
3. `react-router-dom` is installed but unused (see Stack above).
4. No responsive nav / mobile chat-panel-as-full-screen treatment — the chat
   panel is a fixed `max-w-md` slide-over on all viewports, which works down
   to mobile widths but hasn't been given mobile-specific polish.
