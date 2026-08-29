import type { PeriodRollup } from "../lib/api";
import { formatMoney } from "../lib/format";
import { SlotNumber } from "./SlotNumber";

/**
 * Horizontal strip at the top of the message stream: the three numbers a
 * user checks most often, at a glance before they even ask anything.
 */
export function StatsBar({
  netWorth,
  rollup,
  onNetWorthClick,
  onIncomeClick,
  onSpendingClick,
}: {
  netWorth: number | null;
  rollup: PeriodRollup | null;
  onNetWorthClick?: () => void;
  onIncomeClick?: () => void;
  onSpendingClick?: () => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-3">
      <StatTile label="Net worth" value={netWorth} onClick={onNetWorthClick} />
      <StatTile label="Income" sublabel="this month" value={rollup?.income} tone="positive" onClick={onIncomeClick} />
      <StatTile label="Spending" sublabel="this month" value={rollup?.spending} tone="danger" onClick={onSpendingClick} />
    </div>
  );
}

function StatTile({
  label,
  sublabel,
  value,
  tone = "neutral",
  onClick,
}: {
  label: string;
  sublabel?: string;
  value: number | null | undefined;
  tone?: "neutral" | "positive" | "danger";
  onClick?: () => void;
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
