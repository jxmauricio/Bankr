import { formatRelativeTime } from "../lib/format";

const STALE_AFTER_MS = 36 * 3_600_000;

export function isStale(asOf: string | null | undefined): boolean {
  return Boolean(asOf) && Date.now() - new Date(asOf as string).getTime() > STALE_AFTER_MS;
}

/** Balances are older than a day and a half. */
export function StaleBanner({
  asOf,
  onRefresh,
  isRefreshing,
}: {
  asOf: string;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-[20px] border border-warn/40 bg-warn-soft px-[18px] py-4"
    >
      <svg className="mt-0.5 shrink-0" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-warn)" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="text-sm font-semibold text-ink">Balances are {formatRelativeTime(asOf).replace(" ago", "")} old</span>
        <span className="font-mono text-xs text-ink-soft">
          Last synced {new Date(asOf).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
        </span>
      </div>
      <button
        type="button"
        onClick={onRefresh}
        disabled={isRefreshing}
        className="h-11 shrink-0 cursor-pointer rounded-[14px] bg-raised px-4 text-[13px] font-medium text-ink disabled:opacity-60"
      >
        {isRefreshing ? "Refreshing…" : "Refresh"}
      </button>
    </div>
  );
}

/** One or more banks need the user to sign in again. */
export function RelinkBanner({ banks, onManage }: { banks: string[]; onManage: () => void }) {
  const names = banks.join(", ");
  return (
    <div role="alert" className="flex flex-col gap-3.5 rounded-[20px] border border-negative/45 bg-negative-soft p-5">
      <div className="flex items-start gap-3">
        <svg className="mt-0.5 shrink-0" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-negative)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
          <path d="m4 4 16 16" />
        </svg>
        <div className="flex flex-col gap-1">
          <span className="text-[15px] font-semibold text-ink">
            {names} {banks.length === 1 ? "needs" : "need"} you to sign in again
          </span>
          <span className="text-[13px] leading-relaxed text-ink-soft">
            Until then, answers and net worth leave out {banks.length === 1 ? "this bank" : "these banks"}. Your other
            accounts are current.
          </span>
        </div>
      </div>
      <div>
        <button
          type="button"
          onClick={onManage}
          className="h-11 cursor-pointer rounded-[14px] bg-signal px-[18px] text-sm font-semibold text-bg"
        >
          Fix in Settings
        </button>
      </div>
    </div>
  );
}
