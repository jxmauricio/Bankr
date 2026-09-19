import type { PeriodRollup } from "../lib/api";
import { formatMoney, formatRelativeTime } from "../lib/format";
import { SlotNumber } from "./SlotNumber";

/**
 * Horizontal strip at the top of the message stream: the numbers a user
 * checks most often -- net worth, and this month's income, spending, and the
 * gap between them -- on screen before they even ask anything. Labeled
 * with the exact dates and how fresh the data is, so none of them needs
 * checking against the bank.
 */
export function StatsBar({
  netWorth,
  rollup,
  onNetWorthClick,
  onIncomeClick,
  onSpendingClick,
  onRefresh,
  isRefreshing = false,
}: {
  netWorth: number | null;
  rollup: PeriodRollup | null;
  onNetWorthClick?: () => void;
  onIncomeClick?: () => void;
  onSpendingClick?: () => void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}) {
  const range = rollup ? shortRange(rollup.start, rollup.end) : "this month";
  const gap = rollup?.gain;
  return (
    <div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Net worth" value={netWorth} onClick={onNetWorthClick} />
        <StatTile label="Income" sublabel={range} value={rollup?.income} tone="positive" onClick={onIncomeClick} />
        <StatTile
          label="Spending"
          sublabel={range}
          value={rollup?.spending}
          tone="danger"
          onClick={onSpendingClick}
          footnote={rollup && rollup.pending_spending > 0 ? `${formatMoney(rollup.pending_spending)} pending` : undefined}
        />
        <StatTile
          label={gap !== undefined && gap < 0 ? "Overspent" : "Left over"}
          sublabel={range}
          value={gap !== undefined ? Math.abs(gap) : undefined}
          tone={gap !== undefined && gap < 0 ? "danger" : "positive"}
        />
      </div>
      <div className="mt-1.5 flex items-center justify-end gap-2 px-1 text-[11px] text-ink-faint">
        {rollup?.as_of && <span>Updated {formatRelativeTime(rollup.as_of)}</span>}
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            className="underline decoration-dotted underline-offset-2 transition-colors hover:text-ink disabled:no-underline disabled:opacity-60 cursor-pointer"
          >
            {isRefreshing ? "Refreshing…" : "Refresh"}
          </button>
        )}
      </div>
    </div>
  );
}

/** "Sep 1–19" -- the exact window a tile covers, not a vague "this month". */
function shortRange(startIso: string, endIso: string): string {
  const parse = (iso: string) => {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d);
  };
  const start = parse(startIso);
  const end = parse(endIso);
  const month = (d: Date) => d.toLocaleDateString("en-US", { month: "short" });
  if (start.getTime() === end.getTime()) return `${month(start)} ${start.getDate()}`;
  if (start.getMonth() === end.getMonth()) return `${month(start)} ${start.getDate()}–${end.getDate()}`;
  return `${month(start)} ${start.getDate()} – ${month(end)} ${end.getDate()}`;
}

function StatTile({
  label,
  sublabel,
  value,
  tone = "neutral",
  onClick,
  footnote,
}: {
  label: string;
  sublabel?: string;
  value: number | null | undefined;
  tone?: "neutral" | "positive" | "danger";
  onClick?: () => void;
  footnote?: string;
}) {
  const valueColor = tone === "positive" ? "text-positive" : tone === "danger" ? "text-danger" : "text-ink";
  const body = (
    <>
      <div className="text-xs font-medium text-ink-faint">
        {label}
        {sublabel && <span className="text-ink-faint/70"> · {sublabel}</span>}
      </div>
      <div className={`mt-1 truncate font-tabular text-sm font-semibold sm:text-lg ${valueColor}`}>
        {value !== null && value !== undefined ? <SlotNumber value={formatMoney(value)} /> : <SkeletonLine />}
      </div>
      {footnote && <div className="mt-0.5 truncate text-[11px] text-ink-faint">{footnote}</div>}
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="min-w-0 rounded-xl border border-border bg-surface p-3 text-left transition-colors hover:border-accent hover:bg-accent-soft cursor-pointer sm:p-3.5"
      >
        {body}
      </button>
    );
  }

  return <div className="min-w-0 rounded-xl border border-border bg-surface p-3 sm:p-3.5">{body}</div>;
}

function SkeletonLine() {
  return <div className="h-5 w-16 animate-pulse rounded bg-bg" />;
}
