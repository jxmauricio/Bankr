import { useEffect, useState, type ReactNode } from "react";
import { usePlaidLink } from "react-plaid-link";
import { ApiError, fetchLinkToken, linkAccount } from "../lib/api";
import { LINK_TOKEN_KEY, isOAuthReturn, leaveOAuthReturn } from "../lib/plaidOAuth";
import { useSession } from "../lib/session";
import { SetupHeader, StepEyebrow } from "../components/SetupHeader";

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
    <div className="flex min-h-screen flex-col">
      <SetupHeader step={1} />
      <div className="mx-auto flex w-full max-w-[1080px] flex-1 flex-wrap items-start gap-16 px-6 py-12 sm:px-8 sm:py-14">
        <section className="flex min-w-0 flex-[1_1_420px] flex-col gap-7">
          <StepEyebrow>STEP 1 OF 2</StepEyebrow>
          <h1 className="font-display text-[34px] font-normal leading-[1.08] tracking-[-0.02em] text-ink sm:text-[46px]">
            Link the accounts you want Bankr to read.
          </h1>
          <p className="max-w-[480px] text-base leading-relaxed text-ink-soft">
            Checking, savings and credit cards give the clearest picture. You can add or remove banks later in Settings.
          </p>
          <div className="flex flex-col items-start gap-3">
            <button
              type="button"
              disabled={!ready || isBusy}
              onClick={() => open()}
              className="flex h-[52px] cursor-pointer items-center gap-2.5 rounded-xl bg-ink px-6 text-base font-medium text-bg transition-opacity disabled:cursor-default disabled:opacity-60"
            >
              <LockIcon />
              {isSyncing ? "Syncing your accounts…" : "Connect securely with Plaid"}
            </button>
            <span className="text-[13px] text-ink-faint">Opens Plaid in a secure window · about 1 minute</span>
          </div>
          {error && (
            <p role="alert" className="text-sm text-negative">
              {error}
            </p>
          )}
          <div className="flex flex-col gap-1 rounded-xl border border-dashed border-line-strong p-[18px]">
            <span className="text-sm text-ink">Linked accounts</span>
            <span role="status" className="text-[13px] text-ink-faint">
              {isSyncing ? "Reading balances and transactions…" : "None yet. They’ll appear as •••• 1234 once linked."}
            </span>
          </div>
        </section>

        <aside
          aria-label="How your data is protected"
          className="flex min-w-0 flex-[1_1_340px] flex-col gap-[22px] rounded-3xl border border-line bg-surface p-7"
        >
          <h2 className="font-display text-[22px] font-medium text-ink">What Bankr can and can’t do</h2>
          <Assurance icon={<EyeIcon />} title="Read-only">
            Bankr sees balances and transactions. It can’t move money, pay bills or trade.
          </Assurance>
          <Assurance icon={<LockIcon size={22} />} title="Your bank login stays with Plaid">
            You sign in to your bank inside Plaid. Bankr never sees your bank password.
          </Assurance>
          <Assurance icon={<MaskIcon />} title="Account numbers stay masked">
            Everywhere in Bankr you’ll only see the last four digits.
          </Assurance>
          <Assurance icon={<TrashIcon />} title="Leave anytime">
            Unlink a bank or delete your account and data from Settings.
          </Assurance>
          <a href="/privacy" className="text-sm text-signal hover:text-signal-hi">
            Read the privacy notice →
          </a>
        </aside>
      </div>
    </div>
  );
}

function Assurance({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-3.5">
      <span className="shrink-0 text-signal">{icon}</span>
      <div className="flex flex-col gap-1">
        <span className="text-[15px] font-medium text-ink">{title}</span>
        <span className="text-sm leading-relaxed text-ink-soft">{children}</span>
      </div>
    </div>
  );
}

const iconProps = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
} as const;

function LockIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...iconProps} strokeWidth={1.8}>
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" {...iconProps}>
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function MaskIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" {...iconProps}>
      <path d="M4 8h16M4 16h16" />
      <circle cx="8" cy="12" r="1" />
      <circle cx="12" cy="12" r="1" />
      <circle cx="16" cy="12" r="1" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" {...iconProps}>
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
    </svg>
  );
}
