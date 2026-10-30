import { useEffect, useState } from "react";
import { ApiError, decideOAuthRequest, fetchOAuthRequest, type OAuthRequest } from "../lib/api";
import { useSession } from "../lib/session";
import { ThemeToggle } from "../components/ThemeToggle";
import { AuthPage } from "./AuthPage";

type Access = "read" | "write";

const OPTIONS: { value: Access; title: string; detail: string }[] = [
  {
    value: "read",
    title: "Read only",
    detail: "See your balances, spending, goals and transactions.",
  },
  {
    value: "write",
    title: "Read + propose changes",
    detail:
      "Also suggest goals, categorization rules, budget moves and category changes. Nothing changes until you confirm it in Bankr.",
  },
];

/**
 * OAuth consent for an MCP connector (Claude, ChatGPT, ...): the backend's
 * /oauth/authorize sends the browser here with ?request=<id>. The user picks
 * read or read + write, and we send the browser back to the app.
 */
export function ConsentPage() {
  const { token, isAuthenticated, signOut } = useSession();
  const requestId = new URLSearchParams(window.location.search).get("request");
  const [request, setRequest] = useState<OAuthRequest | null>(null);
  const [error, setError] = useState<string | null>(requestId ? null : "This link is missing its connection request.");
  const [access, setAccess] = useState<Access>("read");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token || !requestId) return;
    fetchOAuthRequest(token, requestId)
      .then(setRequest)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) return signOut();
        setError(err instanceof ApiError ? err.message : "Couldn't reach Bankr. Check your connection.");
      });
  }, [token, requestId, signOut]);

  if (!isAuthenticated) return <AuthPage />;

  async function decide(approve: boolean) {
    if (!token || !requestId) return;
    setBusy(true);
    setError(null);
    try {
      const { redirect_to } = await decideOAuthRequest(token, requestId, approve, access === "write");
      window.location.assign(redirect_to);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that. Try again.");
      setBusy(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-bg px-4 py-10">
      <div className="absolute right-3 top-3 sm:right-5 sm:top-5">
        <ThemeToggle />
      </div>
      <main className="w-full max-w-[440px] rounded-3xl border border-line-strong bg-surface p-6 shadow-modal sm:p-8">
        <div className="flex items-baseline gap-2.5">
          <span className="font-display text-[22px] font-bold tracking-tight text-ink">Bankr</span>
          <span className="font-mono text-[10px] tracking-[0.14em] text-signal">CONNECT AN APP</span>
        </div>

        {!request && !error && <p className="mt-6 text-sm text-ink-faint">Loading…</p>}

        {request && (
          <>
            <h1 className="mt-6 font-display text-2xl font-semibold leading-tight text-ink">
              {request.client_name} wants to connect to your Bankr account
            </h1>
            <p className="mt-2 text-sm text-ink-soft">
              Signed in as <span className="text-ink">{request.account_email}</span>.{" "}
              <button type="button" onClick={signOut} className="cursor-pointer text-signal hover:text-signal-hi">
                Not you?
              </button>
            </p>

            <fieldset className="mt-6 flex flex-col gap-2.5">
              <legend className="mb-2 text-sm font-medium text-ink-soft">What can it do?</legend>
              {OPTIONS.map((o) => (
                <label
                  key={o.value}
                  className={`flex cursor-pointer gap-3 rounded-[14px] border p-3.5 ${
                    access === o.value ? "border-signal bg-signal-wash" : "border-line hover:border-line-strong"
                  }`}
                >
                  <input
                    type="radio"
                    name="access"
                    value={o.value}
                    checked={access === o.value}
                    onChange={() => setAccess(o.value)}
                    className="mt-1 accent-[var(--color-signal)]"
                  />
                  <span>
                    <span className="block text-[15px] font-semibold text-ink">{o.title}</span>
                    <span className="mt-0.5 block text-[13px] text-ink-soft">{o.detail}</span>
                  </span>
                </label>
              ))}
            </fieldset>

            <ul className="mt-5 space-y-1.5 text-[13px] text-ink-soft">
              <li>It can never move money, trade, or change your bank connections.</li>
              <li>You can disconnect it any time in Settings.</li>
              {request.redirect_host && (
                <li>
                  You'll be sent back to <span className="font-medium text-ink">{request.redirect_host}</span>.
                </li>
              )}
            </ul>
            {request.redirect_is_loopback && (
              <p className="mt-4 rounded-xl bg-raised p-3 text-[13px] text-ink-soft">
                This app runs on your own computer. Only continue if you started this connection yourself, for
                example from Claude Code.
              </p>
            )}
          </>
        )}

        {error && (
          <p role="alert" className="mt-6 text-sm text-negative">
            {error}
          </p>
        )}

        {request && (
          <div className="mt-6 flex gap-2">
            <button
              type="button"
              onClick={() => decide(true)}
              disabled={busy}
              className="h-11 flex-1 cursor-pointer rounded-[14px] bg-signal text-sm font-semibold text-bg hover:bg-signal-hi disabled:opacity-60"
            >
              {busy ? "Connecting…" : `Allow ${access === "write" ? "read + propose" : "read only"}`}
            </button>
            <button
              type="button"
              onClick={() => decide(false)}
              disabled={busy}
              className="h-11 cursor-pointer rounded-[14px] px-4 text-sm text-ink-soft hover:text-ink disabled:opacity-60"
            >
              Cancel
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
