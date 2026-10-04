import type { GoalProgress } from "../lib/api";
import { GoalPaceTrack } from "./GoalPaceTrack";
import { NewGoalButton } from "./CreateGoalModal";

const MAX_GOALS = 5;

/**
 * Goal cards beside the chat column on wide screens. Hidden below `lg`;
 * HomePage renders the same cards stacked above the chat there.
 */
export function GoalSidebar({
  goals,
  token,
  onGoalDeleted,
  onCreateGoal,
}: {
  goals: GoalProgress[];
  token: string | null;
  onGoalDeleted?: () => void | Promise<void>;
  onCreateGoal: () => void;
}) {
  const slotsLeft = MAX_GOALS - goals.length;
  return (
    <aside aria-label="Goals" className="hidden w-[300px] shrink-0 flex-col py-3 pl-7 pr-2 lg:flex">
      <div className="flex items-baseline justify-between px-1 pb-3">
        <span className="text-sm font-semibold text-ink">Goals</span>
        <span className="font-mono text-[11px] text-ink-faint">
          {goals.length} of {MAX_GOALS}
        </span>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
        {goals.length === 0 && (
          <div className="flex flex-col gap-3 rounded-[20px] bg-surface p-5">
            <span className="text-[15px] font-semibold text-ink">Give your money a job</span>
            <span className="text-[13px] leading-relaxed text-ink-soft">
              Save toward something, or keep a category under a monthly limit. Bankr tracks your pace from your real
              transactions.
            </span>
          </div>
        )}
        {goals.map((goal) => (
          <GoalPaceTrack key={goal.id} progress={goal} token={token} onDeleted={onGoalDeleted} />
        ))}
      </div>
      <div className="mt-3 shrink-0">
        <NewGoalButton onClick={onCreateGoal} />
        <p className="mt-2 text-center text-xs text-ink-faint">
          {slotsLeft > 0
            ? `${slotsLeft} slot${slotsLeft === 1 ? "" : "s"} left · the tick marks today’s pace`
            : "You’ve used all 5 goals. Remove one to add another."}
        </p>
      </div>
    </aside>
  );
}
