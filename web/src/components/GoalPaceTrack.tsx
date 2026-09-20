import { useEffect, useState } from "react";
import { ApiError, deleteGoal, type GoalProgress } from "../lib/api";
import { formatMoney } from "../lib/format";

/**
 * The signature dashboard element: unlike a plain progress bar, this plots
 * both where you actually are (solid fill) and where you'd need to be to
 * hit the target date on schedule (the pace marker) on the same track, so
 * "ahead" or "behind" is visible at a glance rather than left to a number.
 *
 * Spending trackers reuse the same card: remaining budget as the hero
 * number, fill toward the cap, and the same gold pace marker for where
 * even spending would be this far into the window.
 */
export function GoalPaceTrack({
  progress,
  token,
  onDeleted,
}: {
  progress: GoalProgress;
  token: string | null;
  onDeleted?: () => void | Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);

  if (progress.type !== "track_spending" && (!progress.type || progress.target_amount === undefined)) {
    return null;
  }

  return (
    <>
      <div className="relative">
        {token && (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            aria-label={`Delete ${goalTitle(progress)}`}
            className="absolute right-3 top-3 rounded-md p-1 text-ink-faint transition-colors hover:bg-bg hover:text-danger cursor-pointer"
          >
            <TrashIcon />
          </button>
        )}
        {progress.type === "track_spending" ? (
          <SpendingTrackerTrack progress={progress} />
        ) : (
          <SavingsGoalTrack progress={progress} />
        )}
      </div>
      {confirming && token && (
        <DeleteGoalModal
          progress={progress}
          token={token}
          onCancel={() => setConfirming(false)}
          onDeleted={async () => {
            setConfirming(false);
            await onDeleted?.();
          }}
        />
      )}
    </>
  );
}

function SavingsGoalTrack({ progress }: { progress: GoalProgress }) {
  const fraction = Math.min(progress.progress_fraction ?? 0, 1);
  const expected = progress.expected_progress_fraction;
  const onPace = progress.on_pace;

  return (
    <div className="rounded-xl border border-border bg-surface p-5 pr-10">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-ink-soft">{goalTitle(progress)}</span>
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

function SpendingTrackerTrack({ progress }: { progress: GoalProgress }) {
  const spent = progress.current_progress_amount ?? 0;
  const budget = progress.target_amount > 0 ? progress.target_amount : null;
  const remaining = budget != null ? (progress.remaining_amount ?? budget - spent) : null;
  const over = Boolean(progress.over_budget);
  const expected = progress.expected_progress_fraction;
  const ahead = Boolean(budget && !over && progress.on_pace === false);
  const fraction = budget ? Math.min(Math.max(spent / budget, 0), 1) : null;
  const title = progress.name || progress.category || "Spending";
  const period = progress.window_label || progress.window || "";

  let badge: { label: string; className: string } | null = null;
  if (over) badge = { label: "Over budget", className: "bg-danger-soft text-danger" };
  else if (ahead) badge = { label: "Ahead of pace", className: "bg-gold-soft text-gold-strong" };
  else if (budget && expected !== undefined) badge = { label: "On pace", className: "bg-positive-soft text-positive" };
  else if (budget) badge = { label: "On track", className: "bg-positive-soft text-positive" };

  return (
    <div className="rounded-xl border border-border bg-surface p-5 pr-10">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-ink-soft">{title}</span>
        {badge && (
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.className}`}>{badge.label}</span>
        )}
      </div>

      {budget && remaining != null ? (
        <>
          <div className="mt-3 flex items-baseline gap-1.5">
            <span className={`font-tabular text-2xl font-semibold ${over ? "text-danger" : "text-ink"}`}>
              {formatMoney(Math.abs(remaining))}
            </span>
            <span className="text-sm text-ink-faint">{over ? "over" : "left"}</span>
          </div>
          <div className="mt-0.5 font-tabular text-xs text-ink-faint">
            {formatMoney(spent)} of {formatMoney(budget)}
          </div>
        </>
      ) : (
        <div className="mt-3 flex items-baseline gap-1.5">
          <span className="font-tabular text-2xl font-semibold text-ink">{formatMoney(spent)}</span>
          <span className="text-sm text-ink-faint">spent</span>
        </div>
      )}

      {fraction !== null && (
        <div className="relative mt-4 h-2.5 rounded-full bg-bg">
          <div
            className={`h-full rounded-full transition-[width] ${
              over ? "bg-danger" : ahead ? "bg-gold" : "bg-accent"
            }`}
            style={{ width: `${fraction * 100}%` }}
          />
          {expected !== undefined && (
            <div
              className="absolute top-1/2 h-3.5 w-0.5 -translate-y-1/2 rounded-full bg-gold"
              style={{ left: `${Math.min(expected, 1) * 100}%` }}
              title="Even spend through this window"
            />
          )}
        </div>
      )}

      <div className="mt-2 flex justify-between text-xs text-ink-faint">
        <span>{period}</span>
        {progress.label && <span>{progress.label}</span>}
      </div>
    </div>
  );
}

function DeleteGoalModal({
  progress,
  token,
  onCancel,
  onDeleted,
}: {
  progress: GoalProgress;
  token: string;
  onCancel: () => void;
  onDeleted: () => void | Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const title = goalTitle(progress);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !isBusy) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, isBusy]);

  async function handleDelete() {
    setError(null);
    setIsBusy(true);
    try {
      await deleteGoal(token, progress.id);
      await onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete this goal. Try again.");
      setIsBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={() => {
        if (!isBusy) onCancel();
      }}
      role="presentation"
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-border bg-surface p-6"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-goal-title"
      >
        <h2 id="delete-goal-title" className="font-display text-lg font-semibold text-ink">
          Delete {title}?
        </h2>
        <p className="mt-2 text-sm text-ink-soft">
          It’ll come off the left. You can add another anytime with New goal.
        </p>
        {error && (
          <p role="alert" className="mt-3 text-sm text-danger">
            {error}
          </p>
        )}
        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isBusy}
            className="flex-1 rounded-lg border border-border py-2 text-sm text-ink-soft transition-colors hover:border-ink-faint hover:text-ink disabled:opacity-60 cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={isBusy}
            className="flex-1 rounded-lg bg-danger py-2 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-60 cursor-pointer"
          >
            {isBusy ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

function goalTitle(progress: GoalProgress): string {
  if (progress.name?.trim()) return progress.name.trim();
  if (progress.type === "track_spending") return progress.category || "this tracker";
  return "this goal";
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M4 7h16" strokeLinecap="round" />
      <path d="M10 11v6M14 11v6" strokeLinecap="round" />
      <path d="M6 7l1 14h10l1-14" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9 7V4h6v3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
