import { useEffect, useState } from "react";
import { fetchRollupWindow, type PeriodRollup } from "../lib/api";
import { formatMoney, formatRelativeTime } from "../lib/format";
import { SlotNumber } from "./SlotNumber";
import { netWorthChange } from "./NetWorthTrend";
import { periodInfo, windowHistory, type Period } from "../lib/period";
import { isStale } from "./StatusBanners";

/** Compact home-screen numbers: net worth plus this period's income, spending,
 * and leftover. Detail lives behind the net-worth click (cash-flow modal). */
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
  showStale = true,
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
  showStale?: boolean;
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
  const change = netWorthChange(windowed, 1);
  const stale = Boolean(showStale && asOf && isStale(asOf) && !isRefreshing);
  const ageLabel = asOf ? formatRelativeTime(asOf).replace(" ago", "") : "";

  return (
    <section aria-label="Summary" className="rounded-2xl bg-surface px-4 py-3">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onNetWorthClick}
          aria-label="Net worth — open cash-flow view"
          className="min-w-0 shrink-0 text-left cursor-pointer"
        >
          <div className="text-[11px] font-medium text-ink-soft">Net worth</div>
          {netWorth !== null ? (
            <div
              className={`truncate font-mono text-xl font-medium tabular-nums leading-tight ${
                isRefreshing ? "text-ink-soft" : "text-ink"
              }`}
            >
              <SlotNumber value={formatMoney(netWorth)} />
            </div>
          ) : (
            <div className="mt-0.5 h-6 w-28 animate-pulse rounded bg-raised" />
          )}
        </button>

        <div className="hidden h-8 w-px shrink-0 bg-line sm:block" />

        <div className="grid min-w-0 flex-1 grid-cols-3 gap-2">
          <MiniFigure label="Income" value={flow?.income} tone="text-positive" />
          <MiniFigure label="Spending" value={flow?.spending} tone="text-negative" />
          <MiniFigure
            label={flow && flow.gain < 0 ? "Overspent" : "Left over"}
            value={flow ? Math.abs(flow.gain) : undefined}
            tone={flow && flow.gain < 0 ? "text-negative" : "text-positive"}
          />
        </div>

        {onRefresh && (
          <div
            className={`-mr-1 flex shrink-0 items-center ${stale ? "rounded-lg bg-warn-soft" : ""}`}
          >
            {stale && (
              <span role="status" className="flex items-center gap-1 pl-2.5 text-[11px] font-medium text-warn whitespace-nowrap">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7v5l3 2" />
                </svg>
                {ageLabel} old
              </span>
            )}
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              aria-label={
                isRefreshing
                  ? "Refreshing from bank"
                  : stale
                    ? `Balances are ${ageLabel} old — refresh from bank`
                    : "Refresh from bank"
              }
              title={
                stale && asOf
                  ? `Last synced ${new Date(asOf).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
                  : undefined
              }
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors disabled:opacity-60 cursor-pointer ${
                stale ? "text-warn hover:text-ink" : "text-ink-faint hover:text-ink"
              }`}
            >
              <svg
                width="15"
                height="15"
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
          </div>
        )}
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] text-ink-faint">
        {isRefreshing ? (
          <span role="status" className="font-mono text-signal">
            Syncing {bankCount ? `${bankCount} bank${bankCount === 1 ? "" : "s"}` : "your banks"}…
          </span>
        ) : (
          asOf && (
            <span className={`font-mono ${stale ? "text-warn" : ""}`}>
              Updated {formatRelativeTime(asOf)}
              {accountCount ? <span className="hidden sm:inline"> · {accountCount} accounts</span> : null}
            </span>
          )
        )}
        {flow?.label && <span>· {flow.label}</span>}
        {change && (
          <span className={change.delta >= 0 ? "text-positive" : "text-negative"}>
            {change.delta >= 0 ? "+" : "−"}
            {formatMoney(Math.abs(change.delta))}
          </span>
        )}
        {excludedCount > 0 && (
          <span className="text-negative">
            Excludes {excludedCount} account{excludedCount === 1 ? "" : "s"}
          </span>
        )}
      </div>
    </section>
  );
}

function MiniFigure({ label, value, tone }: { label: string; value: number | undefined; tone: string }) {
  return (
    <div className="min-w-0">
      <div className="truncate text-[11px] text-ink-soft">{label}</div>
      <div className={`truncate font-mono text-sm font-medium tabular-nums ${tone}`}>
        {value !== undefined ? formatMoney(value) : <div className="h-4 w-12 animate-pulse rounded bg-line" />}
      </div>
    </div>
  );
}
