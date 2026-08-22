import { useEffect, useState } from "react";
import { usePlaidLink } from "react-plaid-link";
import { ApiError, fetchLinkToken, linkAccount } from "../lib/api";
import { useSession } from "../lib/session";

export function LinkBankPage({ onLinked }: { onLinked: () => void }) {
  const { token } = useSession();
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetchLinkToken(token)
      .then((res) => setLinkToken(res.link_token))
      .catch(() => setError("Couldn't start bank linking. Check your connection and try again."));
  }, [token]);

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess: (publicToken) => {
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
      if (plaidError) setError(plaidError.display_message ?? "Bank linking was interrupted. Try again.");
    },
  });

  const isBusy = !linkToken || isSyncing;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6">
      <div className="w-full max-w-sm text-center">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-soft text-accent">
          <BankIcon />
        </div>
        <h1 className="font-display text-2xl font-semibold text-ink">Link your bank</h1>
        <p className="mt-2 text-ink-soft">
          Bankr reads your balances and transactions to build your dashboard and track your goal.
        </p>

        {error && (
          <p role="alert" className="mt-4 text-sm text-danger">
            {error}
          </p>
        )}

        <button
          type="button"
          disabled={!ready || isBusy}
          onClick={() => open()}
          className="mt-8 w-full rounded-lg bg-accent py-2.5 font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-60 cursor-pointer"
        >
          {isSyncing ? "Syncing your accounts…" : "Connect a bank account"}
        </button>
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
