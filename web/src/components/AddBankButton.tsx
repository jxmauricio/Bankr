import { useEffect, useState } from "react";
import { usePlaidLink } from "react-plaid-link";
import { ApiError, fetchLinkToken, linkAccount } from "../lib/api";
import { LINK_TOKEN_KEY, isOAuthReturn, leaveOAuthReturn } from "../lib/plaidOAuth";

/** Launches Plaid Link to connect an additional bank. Also resumes Link when
 * the user lands back from an OAuth bank's own site. */
export function AddBankButton({
  token,
  disabled,
  onBusyChange,
  onLinked,
}: {
  token: string;
  disabled?: boolean;
  onBusyChange?: (busy: boolean) => void;
  onLinked: () => void | Promise<void>;
}) {
  const [resumingOAuth] = useState(() => isOAuthReturn() && localStorage.getItem(LINK_TOKEN_KEY) !== null);
  const [linkToken, setLinkToken] = useState<string | null>(() =>
    resumingOAuth ? localStorage.getItem(LINK_TOKEN_KEY) : null
  );
  const [isStarting, setIsStarting] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const busy = isStarting || isSyncing;
  useEffect(() => onBusyChange?.(busy), [busy, onBusyChange]);

  const { open, ready } = usePlaidLink({
    token: linkToken,
    receivedRedirectUri: resumingOAuth ? window.location.href : undefined,
    onSuccess: async (publicToken) => {
      leaveOAuthReturn();
      setLinkToken(null);
      setIsStarting(false);
      if (!publicToken) return;
      setIsSyncing(true);
      try {
        await linkAccount(token, publicToken);
        await onLinked();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Couldn't sync this bank. Try again.");
      } finally {
        setIsSyncing(false);
      }
    },
    onExit: (plaidError) => {
      leaveOAuthReturn();
      setLinkToken(null);
      setIsStarting(false);
      if (plaidError) setError(plaidError.display_message ?? "Bank linking was interrupted. Try again.");
    },
  });

  // Open as soon as a fresh token is ready (or when resuming after OAuth).
  useEffect(() => {
    if (linkToken && ready) open();
  }, [linkToken, ready, open]);

  async function start() {
    setError(null);
    setIsStarting(true);
    try {
      const res = await fetchLinkToken(token);
      localStorage.setItem(LINK_TOKEN_KEY, res.link_token);
      setLinkToken(res.link_token);
    } catch {
      setIsStarting(false);
      setError("Couldn't start bank linking. Check your connection and try again.");
    }
  }

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={start}
        disabled={disabled || busy}
        className="w-full min-h-11 rounded-[14px] bg-raised px-3 py-2 text-sm font-medium text-ink transition-colors hover:bg-raised disabled:opacity-60 cursor-pointer"
      >
        {isSyncing ? "Syncing your accounts…" : isStarting ? "Opening…" : "+ Add a bank"}
      </button>
      {error && (
        <p role="alert" className="mt-2 text-sm text-negative">
          {error}
        </p>
      )}
    </div>
  );
}
