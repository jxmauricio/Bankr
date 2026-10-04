import { useEffect, useState } from "react";
import { usePlaidLink } from "react-plaid-link";
import { ApiError, fetchLinkToken, linkAccount } from "../lib/api";
import { LINK_TOKEN_KEY, isOAuthReturn, leaveOAuthReturn } from "../lib/plaidOAuth";
import { useSession } from "../lib/session";

export function LinkBankPage({ onLinked }: { onLinked: () => void }) {
  const { token } = useSession();
  const [resumingOAuth] = useState(() => isOAuthReturn() && localStorage.getItem(LINK_TOKEN_KEY) !== null);
  const [linkToken, setLinkToken] = useState<string | null>(() =>
    resumingOAuth ? localStorage.getItem(LINK_TOKEN_KEY) : null
  );
  const [error, setError] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);

  useEffect(() => {
    if (!token || resumingOAuth) return;
    leaveOAuthReturn();
    fetchLinkToken(token)
      .then((res) => {
        localStorage.setItem(LINK_TOKEN_KEY, res.link_token);
        setLinkToken(res.link_token);
      })
      .catch(() => setError("Couldn't start bank linking. Check your connection and try again."));
  }, [token, resumingOAuth]);

  const { open, ready } = usePlaidLink({
    token: linkToken,
    receivedRedirectUri: resumingOAuth ? window.location.href : undefined,
    onSuccess: (publicToken) => {
      leaveOAuthReturn();
      if (!token || !publicToken) return;
      setIsSyncing(true);
      linkAccount(token, publicToken)
        .then(() => onLinked())
        .catch((err) => {
          setError(err instanceof ApiError ? err.message : "Linked, but syncing failed. Try again from the dashboard.");
          onLinked();
        });
    },
    onExit: (plaidError) => {
      if (resumingOAuth) leaveOAuthReturn();
      if (plaidError) setError(plaidError.display_message ?? "Bank linking was interrupted. Try again.");
    },
  });

  // Coming back from the bank's site: reopen Link straight away so it can
  // finish the connection, rather than making the user click again.
  useEffect(() => {
    if (resumingOAuth && ready) open();
  }, [resumingOAuth, ready, open]);

  const isBusy = !linkToken || isSyncing;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6">
      <div className="w-full max-w-sm text-center">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-signal text-signal">
          <BankIcon />
        </div>
        <h1 className="font-display text-2xl font-semibold text-ink">Link your bank</h1>
        <p className="mt-2 text-ink-soft">
          Bankr reads your balances and transactions to build your dashboard and track your goal.
        </p>

        {error && (
          <p role="alert" className="mt-4 text-sm text-negative">
            {error}
          </p>
        )}

        <button
          type="button"
          disabled={!ready || isBusy}
          onClick={() => open()}
          className="mt-8 w-full rounded-[14px] bg-accent py-2.5 font-medium text-bg transition-colors hover:bg-accent-strong disabled:opacity-60 cursor-pointer"
        >
          {isSyncing ? "Syncing your accounts…" : "Connect a bank account"}
        </button>
        <ul className="mt-6 space-y-2.5 text-left text-[13px] leading-relaxed text-ink-soft">
          {[
            "Read-only. Bankr can see balances and transactions — it can’t move money.",
            "Your bank login goes to Plaid, never to Bankr.",
            "Disconnect any bank, or delete your account, whenever you like in Settings.",
          ].map((line) => (
            <li key={line} className="flex gap-3">
              <span aria-hidden className="mt-0.5 text-signal">✓</span>
              {line}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function BankIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M3 10.5 12 4l9 6.5M4.5 10.5v8M9 10.5v8M15 10.5v8M19.5 10.5v8M2.5 20h19" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
