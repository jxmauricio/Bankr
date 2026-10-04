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
            className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-lg text-ink-faint transition-colors hover:bg-raised hover:text-negative cursor-pointer"
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

/** Whole dollars on goal cards; cents only when they matter. */
const whole = (n: number) => formatMoney(n).replace(/\.00$/, "");

const CARD = "rounded-[20px] bg-surface px-[18px] py-4 pr-10";

/** The rail: a neutral fill for progress, a tick where steady pace would put
 * you today, and a gap between them that is hatched or coloured by whether it
 * helps (good) or hurts (bad). `fill` and `pace` are 0..1. */
function PaceRail({
  fill,
  pace,
  gap,
  label,
}: {
  fill: number;
  pace: number | undefined;
  gap: "good" | "bad" | "warn" | "none";
  label: string;
}) {
  const f = Math.min(Math.max(fill, 0), 1) * 100;
  const p = pace === undefined ? undefined : Math.min(Math.max(pace, 0), 1) * 100;
  const lo = p === undefined ? f : Math.min(f, p);
  const hi = p === undefined ? f : Math.max(f, p);
  const gapClass =
    gap === "good" ? "bg-positive" : gap === "bad" ? "bg-negative" : gap === "warn" ? "hatch-warn" : "";
  return (
    <div role="img" aria-label={label} className="relative mt-3 h-1.5 rounded-[3px] bg-line">
      <div className="absolute inset-y-0 left-0 rounded-l-[3px] bg-ink-soft" style={{ width: `${lo}%` }} />
      {gap !== "none" && hi > lo && (
        <div className={`absolute inset-y-0 ${gapClass}`} style={{ left: `${lo}%`, width: `${hi - lo}%` }} />
      )}
      {p !== undefined && (
        <div
          className="absolute -top-[5px] h-4 w-0.5 rounded-[1px] bg-ink"
          style={{ left: `calc(${p}% - 1px)` }}
          title="Where steady pace puts you today"
        />
      )}
    </div>
  );
}

function KindTag({ children }: { children: string }) {
  return <span className="font-mono text-[10px] tracking-[0.1em] text-ink-faint">{children}</span>;
}

function SavingsGoalTrack({ progress }: { progress: GoalProgress }) {
  const fraction = Math.min(progress.progress_fraction ?? 0, 1);
  const expected = progress.expected_progress_fraction;
  const onPace = progress.on_pace;
  const reached = fraction >= 1;
  const target = progress.target_amount;
  const gapAmount = expected !== undefined ? Math.abs(expected - fraction) * target : 0;
  const ahead = expected !== undefined && fraction > expected && !reached;
  const behind = onPace === false && !reached;

  return (
    <div className={CARD}>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-semibold text-ink">{goalTitle(progress)}</span>
        <KindTag>SAVE</KindTag>
      </div>
      <div className="mt-2.5 flex items-baseline justify-between gap-2 text-xs text-ink-soft">
        <span>
          <span className="font-mono text-[13px] tabular-nums text-ink">
            {whole(progress.current_progress_amount ?? 0)}
          </span>{" "}
          / <span className="font-mono tabular-nums">{whole(target)}</span>
        </span>
        {progress.target_date && <span className="shrink-0">{progress.target_date}</span>}
      </div>
      {reached ? (
        <div className="mt-3 h-1.5 rounded-[3px] bg-signal" role="img" aria-label="Goal reached" />
      ) : (
        <PaceRail
          fill={fraction}
          pace={expected}
          gap={ahead ? "good" : behind ? "warn" : "none"}
          label={`${Math.round(fraction * 100)}% saved${
            expected !== undefined ? `; pace mark at ${Math.round(expected * 100)}%` : ""
          }. ${reached ? "Reached" : behind ? "Behind" : ahead ? "Ahead" : "On pace"}.`}
        />
      )}
      <div
        className={`mt-2.5 font-mono text-[11px] tabular-nums ${
          reached ? "text-signal" : behind ? "text-warn" : ahead ? "text-positive" : "text-ink-soft"
        }`}
      >
        {reached
          ? "✓ REACHED"
          : behind
            ? `▼ BEHIND ${whole(gapAmount)}`
            : ahead
              ? `▲ AHEAD ${whole(gapAmount)}`
              : "● ON PACE"}
      </div>
    </div>
  );
}

function SpendingTrackerTrack({ progress }: { progress: GoalProgress }) {
  const spent = progress.current_progress_amount ?? 0;
  const budget = progress.target_amount > 0 ? progress.target_amount : null;
  const over = Boolean(progress.over_budget);
  const expected = progress.expected_progress_fraction;
  const fraction = budget ? Math.min(Math.max(spent / budget, 0), 1) : null;
  const paceGap = budget && expected !== undefined ? spent - expected * budget : 0;
  const overPace = !over && budget && expected !== undefined && paceGap > budget * 0.02;
  const underPace = !over && budget && expected !== undefined && paceGap < -budget * 0.02;
  const title = progress.name || progress.category || "Spending";
  const period = progress.window_label || progress.window || "";
  const money = (n: number) => whole(Math.abs(n));

  return (
    <div className={CARD}>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-semibold text-ink">{title}</span>
        <KindTag>TRACK</KindTag>
      </div>
      <div className="mt-2.5 flex items-baseline justify-between gap-2 text-xs text-ink-soft">
        <span>
          <span className="font-mono text-[13px] tabular-nums text-ink">{whole(spent)}</span>
          {budget && (
            <>
              {" "}
              / <span className="font-mono tabular-nums">{whole(budget)}</span>
            </>
          )}
          {!budget && " spent"}
        </span>
        <span className="shrink-0">{period}</span>
      </div>
      {fraction !== null &&
        (over ? (
          <div className="relative mt-3 h-1.5 rounded-[3px] bg-negative" role="img" aria-label="Over the limit" />
        ) : (
          <PaceRail
            fill={fraction}
            pace={expected}
            gap={overPace ? "bad" : underPace ? "good" : "none"}
            label={`${Math.round(fraction * 100)}% of budget${
              expected !== undefined ? `; pace mark at ${Math.round(expected * 100)}%` : ""
            }. ${overPace ? "Over pace" : underPace ? "Under pace" : "On pace"}.`}
          />
        ))}
      {budget && (
        <div
          className={`mt-2.5 font-mono text-[11px] tabular-nums ${
            over || overPace ? "text-negative" : underPace ? "text-positive" : "text-ink-soft"
          }`}
        >
          {over
            ? `▲ ${money(spent - budget)} OVER THE ${money(budget)} LIMIT`
            : overPace
              ? `▲ ${money(paceGap)} OVER PACE`
              : underPace
                ? `● ${money(paceGap)} UNDER PACE`
                : "● ON PACE"}
        </div>
      )}
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 px-4"
      onClick={() => {
        if (!isBusy) onCancel();
      }}
      role="presentation"
    >
      <div
        className="w-full max-w-sm rounded-3xl border border-line-strong bg-surface shadow-modal p-6"
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
          <p role="alert" className="mt-3 text-sm text-negative">
            {error}
          </p>
        )}
        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isBusy}
            className="flex-1 min-h-11 rounded-[14px] bg-raised py-2 text-sm text-ink-soft transition-colors hover:text-ink disabled:opacity-60 cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={isBusy}
            className="flex-1 min-h-11 rounded-[14px] bg-negative py-2 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-60 cursor-pointer"
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
