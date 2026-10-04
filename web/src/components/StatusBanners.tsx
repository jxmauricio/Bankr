const STALE_AFTER_MS = 36 * 3_600_000;

export function isStale(asOf: string | null | undefined): boolean {
  return Boolean(asOf) && Date.now() - new Date(asOf as string).getTime() > STALE_AFTER_MS;
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
