import type { GoalProgress } from "../lib/api";
import { GoalPaceTrack } from "./GoalPaceTrack";
import { NewGoalButton } from "./CreateGoalModal";

const MAX_GOALS = 5;

/** The goals half of the money rail: the desktop rail and the phone's dropped sheet both render it. */
export function GoalsSection({
  goals,
  token,
  onGoalDeleted,
  onCreateGoal,
  onSuggestGoal,
}: {
  goals: GoalProgress[];
  token: string | null;
  onGoalDeleted?: () => void | Promise<void>;
  onCreateGoal: () => void;
  onSuggestGoal: () => void;
}) {
  const slotsLeft = MAX_GOALS - goals.length;
  return (
    <section aria-label="Goals" className="flex flex-col">
      <div className="flex items-baseline justify-between px-1 pb-3 pt-1.5">
        <span className="text-[13px] font-semibold text-ink">Goals</span>
        <span className={`font-mono text-[11px] ${slotsLeft > 0 ? "text-ink-faint" : "text-warn"}`}>
          {goals.length} of {MAX_GOALS}
        </span>
      </div>
      <div className="flex flex-col gap-3">
        {goals.length === 0 && <EmptyGoals onCreateGoal={onCreateGoal} onSuggestGoal={onSuggestGoal} />}
        {goals.map((goal) => (
          <GoalPaceTrack key={goal.id} progress={goal} token={token} onDeleted={onGoalDeleted} />
        ))}
      </div>
      {goals.length > 0 && (
        <div className="mt-3 shrink-0">
          <NewGoalButton onClick={onCreateGoal} disabled={slotsLeft <= 0} />
          <p className="mt-2 text-center text-xs text-ink-faint">
            {slotsLeft > 0
              ? `${slotsLeft} slot${slotsLeft === 1 ? "" : "s"} left · the tick marks today’s pace`
              : "You’ve used all 5 goals. Remove one to add another."}
          </p>
        </div>
      )}
    </section>
  );
}

/** No goals yet: an empty pace track and two ways to start one. */
export function EmptyGoals({ onCreateGoal, onSuggestGoal }: { onCreateGoal: () => void; onSuggestGoal: () => void }) {
  return (
    <div className="flex flex-col gap-3.5 rounded-[20px] bg-surface p-[22px]">
      <div aria-hidden className="relative h-1.5 rounded-[3px] bg-line">
        <div className="absolute -top-[5px] left-[40%] h-4 w-0.5 bg-line-strong" />
      </div>
      <span className="text-[15px] font-semibold text-ink">Give your money a job</span>
      <span className="text-[13px] leading-relaxed text-ink-soft">
        Save toward something, or keep a category under a monthly limit. Bankr tracks your pace from your real
        transactions.
      </span>
      <button
        type="button"
        onClick={onCreateGoal}
        className="h-11 cursor-pointer rounded-[14px] bg-signal text-sm font-semibold text-bg hover:bg-signal-hi"
      >
        + New goal
      </button>
      <button
        type="button"
        onClick={onSuggestGoal}
        className="h-11 cursor-pointer rounded-[14px] bg-raised text-[13px] text-ink-soft hover:text-ink"
      >
        Ask Bankr to suggest one
      </button>
    </div>
  );
}
