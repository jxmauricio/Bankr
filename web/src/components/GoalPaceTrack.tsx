import type { GoalProgress } from "../lib/api";
import { formatMoney, GOAL_TYPE_LABELS } from "../lib/format";

/**
 * The signature dashboard element: unlike a plain progress bar, this plots
 * both where you actually are (solid fill) and where you'd need to be to
 * hit the target date on schedule (the pace marker) on the same track, so
 * "ahead" or "behind" is visible at a glance rather than left to a number.
 */
export function GoalPaceTrack({ progress }: { progress: GoalProgress }) {
  if (!progress.type || progress.target_amount === undefined) {
    return null;
  }

  const fraction = Math.min(progress.progress_fraction ?? 0, 1);
  const expected = progress.expected_progress_fraction;
  const onPace = progress.on_pace;

  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-ink-soft">{GOAL_TYPE_LABELS[progress.type] ?? progress.type}</span>
        {onPace !== undefined && (
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
              onPace ? "bg-positive-soft text-positive" : "bg-gold-soft text-gold-strong"
            }`}
          >
            {onPace ? "On pace" : "Behind pace"}
          </span>
        )}
      </div>

      <div className="mt-3 flex items-baseline gap-1.5">
        <span className="font-tabular text-2xl font-semibold text-ink">
          {formatMoney(progress.current_progress_amount ?? 0)}
        </span>
        <span className="font-tabular text-ink-faint">/ {formatMoney(progress.target_amount)}</span>
      </div>

      <div className="relative mt-4 h-2.5 rounded-full bg-bg">
        <div
          className="h-full rounded-full bg-accent transition-[width]"
          style={{ width: `${fraction * 100}%` }}
        />
        {expected !== undefined && (
          <div
            className="absolute top-1/2 h-3.5 w-0.5 -translate-y-1/2 rounded-full bg-gold"
            style={{ left: `${Math.min(expected, 1) * 100}%` }}
            title="Where you'd need to be to stay on pace"
          />
        )}
      </div>

      <div className="mt-2 flex justify-between text-xs text-ink-faint">
        <span>{Math.round(fraction * 100)}% there</span>
        {progress.target_date && <span>Target {progress.target_date}</span>}
      </div>
    </div>
  );
}
