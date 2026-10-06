import type { PeriodRollup } from "../lib/api";
import { formatMoney, formatRelativeTime } from "../lib/format";
import { windowHistory } from "../lib/period";
import { netWorthChange } from "./NetWorthTrend";
import { SlotNumber } from "./SlotNumber";
import { isStale } from "./StatusBanners";

type Point = { date: string; net_worth: number };

export type MoneySummary = {
  netWorth: number | null;
  flow: PeriodRollup | null;
  history: Point[];
  asOf?: string | null;
  accountCount?: number;
  excludedCount?: number;
  bankCount?: number;
  isRefreshing?: boolean;
  /** False while a re-link banner already explains why data is behind. */
  showStale?: boolean;
};

/** Whole dollars unless the cents carry meaning. */
const whole = (n: number) => formatMoney(n).replace(/\.\d\d$/, "");

function splitCents(value: number): [string, string] {
  const text = formatMoney(value);
  const dot = text.lastIndexOf(".");
  return dot === -1 ? [text, ""] : [text.slice(0, dot), text.slice(dot)];
}

function changeFor(summary: MoneySummary) {
  return netWorthChange(windowHistory(summary.history, summary.flow?.start, summary.flow?.end), 1);
}

/**
 * The money rail's card: net worth, its change and trend over the header's
 * period, then income and spending as paired bars on one scale so the gap
 * between them reads as what's left over.
 */
export function MoneyCard({
  summary,
  onNetWorthClick,
  onRefresh,
}: {
  summary: MoneySummary;
  onNetWorthClick?: () => void;
  onRefresh?: () => void;
}) {
  const { netWorth, flow, asOf, isRefreshing = false, excludedCount = 0, bankCount, accountCount } = summary;
  const windowed = windowHistory(summary.history, flow?.start, flow?.end);
  const change = changeFor(summary);
  const stale = Boolean((summary.showStale ?? true) && asOf && isStale(asOf) && !isRefreshing);
  const [dollars, cents] = netWorth !== null ? splitCents(netWorth) : ["", ""];

  return (
    <section
      aria-label="Net worth"
      className="flex flex-col gap-2.5 rounded-[20px] bg-surface p-[18px] ring-[1.5px] ring-signal/55"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-ink-soft">Net worth</span>
        {flow?.label && <span className="font-mono text-[10px] tracking-[0.08em] text-ink-faint">{flow.label.toUpperCase()}</span>}
      </div>

      {netWorth !== null ? (
        <button
          type="button"
          onClick={onNetWorthClick}
          aria-label={`Net worth ${formatMoney(netWorth)} — open cash-flow view`}
          className={`flex cursor-pointer items-baseline text-left font-mono font-medium tabular-nums tracking-[-0.04em] ${
            isRefreshing ? "text-ink-soft" : "text-ink"
          }`}
        >
          <SlotNumber value={dollars} className="text-[32px] leading-tight" />
          <span className="text-[17px] text-ink-faint">{cents}</span>
        </button>
      ) : (
        <div className="h-10 w-48 animate-pulse rounded-[10px] bg-raised" />
      )}

      <div className="flex min-h-[26px] items-center justify-between gap-2">
        {change ? (
          <span className={`font-mono text-xs ${change.delta >= 0 ? "text-positive" : "text-negative"}`}>
            {change.delta >= 0 ? "▲ +" : "▼ −"}
            {whole(Math.abs(change.delta))}
            {change.pct !== null && ` · ${Math.abs(change.pct).toFixed(1)}%`}
          </span>
        ) : (
          <span className="text-xs text-ink-faint">No change to show yet</span>
        )}
        <MiniTrend history={windowed} />
      </div>

      <CashFlowBars flow={flow} />

      <div className="flex items-center justify-between gap-2 text-[11px] text-ink-faint">
        {isRefreshing ? (
          <span role="status" className="font-mono text-signal">
            Syncing {bankCount ? `${bankCount} bank${bankCount === 1 ? "" : "s"}` : "your banks"}…
          </span>
        ) : (
          <span className={`font-mono ${stale ? "text-warn" : ""}`}>
            {asOf ? `${stale ? "◷ " : ""}Updated ${formatRelativeTime(asOf)}` : ""}
            {accountCount ? ` · ${accountCount} accounts` : ""}
          </span>
        )}
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label={isRefreshing ? "Refreshing from bank" : "Refresh from bank"}
            title={asOf ? `Last synced ${new Date(asOf).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}` : undefined}
            className={`-mr-2.5 flex h-8 w-11 shrink-0 cursor-pointer items-center justify-center rounded-lg transition-colors hover:text-ink disabled:opacity-60 ${
              stale ? "text-warn" : "text-ink-soft"
            }`}
          >
            <RefreshIcon spinning={isRefreshing} />
          </button>
        )}
      </div>
      {excludedCount > 0 && (
        <span className="text-[11px] text-negative">
          Excludes {excludedCount} account{excludedCount === 1 ? "" : "s"} that need re-linking
        </span>
      )}
    </section>
  );
}

/** Income and spending on one scale; the dashed remainder is what's left over. */
function CashFlowBars({ flow }: { flow: PeriodRollup | null }) {
  if (!flow) {
    return (
      <div className="flex flex-col gap-3 rounded-[14px] bg-raised px-3.5 py-3">
        <div className="h-4 w-full animate-pulse rounded bg-line" />
        <div className="h-4 w-4/5 animate-pulse rounded bg-line" />
      </div>
    );
  }
  const scale = Math.max(flow.income, flow.spending, 1);
  const incomePct = (flow.income / scale) * 100;
  const spendPct = (flow.spending / scale) * 100;
  const overspent = flow.gain < 0;
  const savedPct = flow.income > 0 && !overspent ? Math.round((flow.gain / flow.income) * 100) : null;

  return (
    <div
      role="group"
      aria-label={`${flow.label}: income ${formatMoney(flow.income)}, spending ${formatMoney(flow.spending)}, ${
        overspent ? `${formatMoney(-flow.gain)} overspent` : `${formatMoney(flow.gain)} left over`
      }`}
      className="flex flex-col gap-2.5 rounded-[14px] bg-raised px-3.5 py-3"
    >
      <FlowRow label="Income" arrow="↓" value={flow.income} tone="signal">
        <div className="h-2 rounded bg-line">
          <div className="h-2 rounded bg-signal" style={{ width: `${incomePct}%` }} />
        </div>
      </FlowRow>
      <FlowRow label="Spending" arrow="↑" value={flow.spending} tone="spend">
        <div className="flex h-2 rounded bg-line">
          <div
            className={`h-2 bg-spend ${overspent || incomePct === spendPct ? "rounded" : "rounded-l"}`}
            style={{ width: `${spendPct}%` }}
          />
          {!overspent && incomePct > spendPct && (
            <div
              className="h-2 rounded-r border border-dashed border-positive/70"
              style={{ width: `${incomePct - spendPct}%` }}
            />
          )}
        </div>
      </FlowRow>
      <div className="flex items-baseline justify-between border-t border-line-strong pt-2">
        <span className="text-xs text-ink-soft">{overspent ? "Overspent" : "Left over"}</span>
        <span className={`font-mono text-[13px] ${overspent ? "text-negative" : "text-positive"}`}>
          {overspent ? "−" : "+"}
          {whole(Math.abs(flow.gain))}
          {savedPct !== null && ` · ${savedPct}% saved`}
        </span>
      </div>
    </div>
  );
}

function FlowRow({
  label,
  arrow,
  value,
  tone,
  children,
}: {
  label: string;
  arrow: string;
  value: number;
  tone: "signal" | "spend";
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between">
        <span className="flex items-center gap-1.5 text-xs text-ink-soft">
          <span
            aria-hidden
            className={`flex h-[18px] w-[18px] items-center justify-center rounded-md text-[11px] ${
              tone === "signal" ? "bg-signal/15 text-signal" : "bg-spend/15 text-spend"
            }`}
          >
            {arrow}
          </span>
          {label}
        </span>
        <span className={`font-mono text-[17px] font-medium ${tone === "signal" ? "text-signal" : "text-spend"}`}>
          {whole(value)}
        </span>
      </div>
      {children}
    </div>
  );
}

function MiniTrend({ history }: { history: Point[] }) {
  if (history.length < 2) return null;
  const values = history.map((p) => p.net_worth);
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const path = values
    .map((v, i) => `${i === 0 ? "M" : "L"}${((i / (values.length - 1)) * 600).toFixed(1)} ${(54 - ((v - min) / span) * 48).toFixed(1)}`)
    .join(" ");
  return (
    <svg aria-hidden width="96" height="26" viewBox="0 0 600 60" preserveAspectRatio="none" className="shrink-0">
      <path d={path} stroke="var(--color-signal)" strokeWidth="2" fill="none" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/**
 * The rail collapsed into the phone's top bar: net worth, its change, and a
 * thin bar of spending against income. Tapping it drops the full rail.
 */
export function MoneyPill({
  summary,
  open,
  onToggle,
}: {
  summary: MoneySummary;
  open: boolean;
  onToggle: () => void;
}) {
  const { netWorth, flow } = summary;
  const change = changeFor(summary);
  const [dollars, cents] = netWorth !== null ? splitCents(netWorth) : ["", ""];
  const outOfIn = flow && flow.income > 0 ? Math.round((flow.spending / flow.income) * 100) : null;
  const noIncome = Boolean(flow && flow.income <= 0 && flow.spending > 0);
  const label = [
    netWorth !== null ? `Your money: net worth ${formatMoney(netWorth)}` : "Your money",
    change?.pct != null ? `${change.delta >= 0 ? "up" : "down"} ${Math.abs(change.pct).toFixed(1)}%` : null,
    outOfIn !== null ? `spending is ${outOfIn}% of income` : noIncome ? "no income this period" : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls="money-sheet"
      aria-label={label}
      className={`flex min-w-0 flex-1 cursor-pointer flex-col gap-[7px] rounded-2xl px-3.5 pb-[9px] pt-2 text-left ${
        open ? "bg-raised" : "bg-surface"
      }`}
    >
      <span className="flex w-full items-center justify-between gap-2">
        <span className="flex min-w-0 items-baseline gap-2">
          {netWorth !== null ? (
            <span className="truncate font-mono text-[17px] font-medium tracking-[-0.03em] text-ink">
              {dollars}
              <span className="text-xs text-ink-faint">{cents}</span>
            </span>
          ) : (
            <span className="h-5 w-24 animate-pulse rounded bg-raised" />
          )}
          {change?.pct != null && (
            <span className={`font-mono text-[11px] ${change.delta >= 0 ? "text-positive" : "text-negative"}`}>
              {change.delta >= 0 ? "▲" : "▼"}
              {Math.abs(change.pct).toFixed(1)}%
            </span>
          )}
        </span>
        <svg
          aria-hidden
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--color-ink-soft)"
          strokeWidth="2"
          strokeLinecap="round"
          className={`shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path d="m7 10 5 5 5-5" />
        </svg>
      </span>
      {(outOfIn !== null || noIncome) && (
        <span aria-hidden className="flex w-full items-center gap-2">
          <span className="flex h-1 flex-1 overflow-hidden rounded-sm bg-signal">
            <span className="bg-spend" style={{ width: `${Math.min(outOfIn ?? 100, 100)}%` }} />
          </span>
          <span className="whitespace-nowrap font-mono text-[10px] text-ink-soft">
            {outOfIn !== null ? (
              <>
                <span className="text-spend">out</span> {outOfIn}% of <span className="text-signal">in</span>
              </>
            ) : (
              <>
                <span className="text-spend">out</span> · no income
              </>
            )}
          </span>
        </span>
      )}
    </button>
  );
}

function RefreshIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      className={spinning ? "animate-spin" : undefined}
      aria-hidden
    >
      <path d="M20 11a8 8 0 0 0-14.6-4.5M4 4v4h4M4 13a8 8 0 0 0 14.6 4.5M20 20v-4h-4" />
    </svg>
  );
}
