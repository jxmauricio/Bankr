import { useEffect, useRef, useState } from "react";
import { PERIODS, periodInfo, type Period } from "../lib/period";

/** The app-wide time filter, in the header. Everything on Home that depends on
 * a time range (income, spending, left over, the net worth trend and change)
 * follows it. */
export function PeriodFilter({ period, onChange }: { period: Period; onChange: (period: Period) => void }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const current = periodInfo(period);

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Time period: ${current.label}`}
        className="flex h-11 cursor-pointer items-center gap-2 rounded-full bg-surface pl-4 pr-3 text-[13px] text-ink transition-colors hover:text-signal-hi"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--color-signal)" strokeWidth="1.7" strokeLinecap="round" aria-hidden>
          <rect x="4" y="5" width="16" height="15" rx="3" />
          <path d="M4 10h16M9 3v4M15 3v4" />
        </svg>
        <span className="whitespace-nowrap font-mono">{current.short}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-soft)" strokeWidth="1.7" strokeLinecap="round" aria-hidden>
          <path d="m7 10 5 5 5-5" />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Time period"
          className="absolute right-0 top-full z-20 mt-2 w-52 rounded-[20px] border border-line bg-raised p-1.5 shadow-menu"
        >
          {PERIODS.map((p) => (
            <button
              key={p.value}
              type="button"
              role="menuitemradio"
              aria-checked={p.value === period}
              onClick={() => {
                onChange(p.value);
                setOpen(false);
              }}
              className={`flex min-h-11 w-full cursor-pointer items-center justify-between rounded-xl px-3 text-left text-sm transition-colors hover:bg-surface ${
                p.value === period ? "text-signal-hi" : "text-ink"
              }`}
            >
              {p.label}
              {p.value === period && <span aria-hidden>✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
