import { useEffect, useState } from "react";
import { fetchRollupWindow, type PeriodRollup } from "../lib/api";
import { formatMoney, formatRelativeTime } from "../lib/format";
import { SlotNumber } from "./SlotNumber";
import { ChangePill, Sparkline } from "./NetWorthTrend";
import { periodInfo, windowHistory, type Period } from "../lib/period";

/** The home screen's numbers: net worth, plus income and spending for the
 * period chosen in the header. */
export function AverageBar({
  token,
  period,
  netWorth,
  asOf,
  onNetWorthClick,
  onRefresh,
  isRefreshing = false,
  refreshKey,
  history = [],
  accountCount,
  excludedCount = 0,
  bankCount,
}: {
  token: string;
  period: Period;
  netWorth: number | null;
  asOf?: string | null;
  onNetWorthClick?: () => void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  refreshKey?: unknown;
  history?: { date: string; net_worth: number }[];
  accountCount?: number;
  excludedCount?: number;
  bankCount?: number;
}) {
  const [flow, setFlow] = useState<PeriodRollup | null>(null);
  const info = periodInfo(period);

  useEffect(() => {
    let stale = false;
    setFlow(null);
    fetchRollupWindow(token, info.window)
      .then((r) => !stale && setFlow(r))
      .catch(() => !stale && setFlow(null));
    return () => {
      stale = true;
    };
  }, [token, info.window, refreshKey]);

  const windowed = windowHistory(history, flow?.start, flow?.end);
  const note = flow ? flow.label : null;

  return (
    <section aria-label="Summary" className="rounded-3xl bg-surface p-6">
      <div className="flex items-center justify-between gap-3">
        <span className="shrink-0 whitespace-nowrap text-[13px] font-semibold text-ink-soft">Net worth</span>
        <div className="flex items-center gap-0.5 text-xs text-ink-faint">
          {isRefreshing ? (
            <span role="status" className="flex items-center gap-2 text-signal">
              <span className="font-mono">
                Syncing {bankCount ? `${bankCount} bank${bankCount === 1 ? "" : "s"}` : "your banks"}…
              </span>
            </span>
          ) : (
            asOf && (
              <span className="font-mono">
                Updated {formatRelativeTime(asOf)}
                {accountCount ? <span className="hidden sm:inline"> · {accountCount} accounts</span> : null}
              </span>
            )
          )}
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              aria-label={isRefreshing ? "Refreshing from bank" : "Refresh from bank"}
              className="-my-2.5 -mr-3 flex h-11 w-11 items-center justify-center rounded-xl text-ink-soft transition-colors hover:text-ink disabled:opacity-60 cursor-pointer"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                className={isRefreshing ? "animate-spin" : undefined}
              >
                <path d="M20 11a8 8 0 0 0-14.6-4.5M4 4v4h4M4 13a8 8 0 0 0 14.6 4.5M20 20v-4h-4" />
              </svg>
            </button>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={onNetWorthClick}
        aria-label="Net worth — open cash-flow view"
        className="mt-1 flex items-baseline text-left cursor-pointer"
      >
        {netWorth !== null ? (
          <HeroMoney value={netWorth} dim={isRefreshing} />
        ) : (
          <div className="h-12 w-56 animate-pulse rounded-lg bg-raised" />
        )}
        <svg
          className="ml-2 self-center"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--color-ink-faint)"
          strokeWidth="1.7"
          strokeLinecap="round"
          aria-hidden
        >
          <path d="M7 17 17 7M9 7h8v8" />
        </svg>
      </button>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        {flow ? <ChangePill history={windowed} minDays={1} /> : <div className="h-7 w-44 animate-pulse rounded-full bg-raised" />}
        {excludedCount > 0 && (
          <span className="text-xs text-negative">
            Excludes {excludedCount} account{excludedCount === 1 ? "" : "s"}
          </span>
        )}
      </div>
      {flow && <Sparkline history={windowed} />}

      <h3 className="mt-5 text-xs text-ink-soft">{info.label}</h3>
      <div className="mt-3 grid gap-2 sm:grid-cols-3 sm:gap-3">
        <Figure label="Income" value={flow?.income} tone="text-positive" />
        <Figure label="Spending" value={flow?.spending} tone="text-negative" />
        <Figure
          label={flow && flow.gain < 0 ? "Overspent" : "Left over"}
          value={flow ? Math.abs(flow.gain) : undefined}
          tone={flow && flow.gain < 0 ? "text-negative" : "text-positive"}
        />
      </div>
      {note && <p className="mt-3 text-xs text-ink-faint">{note}</p>}
    </section>
  );
}

/** Dollars at hero size, cents at half size in ink-faint. */
function HeroMoney({ value, dim }: { value: number; dim?: boolean }) {
  const text = formatMoney(value);
  const dot = text.lastIndexOf(".");
  return (
    <span
      className={`font-mono text-5xl font-medium leading-none tracking-[-0.04em] tabular-nums transition-colors ${
        dim ? "text-ink-soft" : "text-ink"
      }`}
    >
      <SlotNumber value={text.slice(0, dot)} />
      <span className="text-2xl text-ink-faint">
        <SlotNumber value={text.slice(dot)} />
      </span>
    </span>
  );
}

function Figure({ label, value, tone }: { label: string; value: number | undefined; tone: string }) {
  return (
    <div className="flex min-w-0 items-baseline justify-between rounded-2xl bg-raised px-3.5 py-3 sm:block">
      <div className="text-xs text-ink-soft">{label}</div>
      <div className={`truncate font-mono text-base font-medium tabular-nums sm:mt-0.5 sm:text-[19px] ${tone}`}>
        {value !== undefined ? formatMoney(value) : <div className="h-5 w-16 animate-pulse rounded bg-line" />}
      </div>
    </div>
  );
}
