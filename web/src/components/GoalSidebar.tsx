import type { GoalProgress } from "../lib/api";
import { GoalPaceTrack } from "./GoalPaceTrack";
import { NewGoalButton } from "./CreateGoalModal";

/**
 * Fills the empty gutter beside the centered chat column on wide screens
 * with goal progress. Hidden below `lg` since there's no spare space to put
 * it in on narrower viewports.
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
  return (
    <aside className="hidden w-72 shrink-0 flex-col border-r border-border p-5 lg:flex">
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
        {goals.map((goal) => (
          <GoalPaceTrack key={goal.id} progress={goal} token={token} onDeleted={onGoalDeleted} />
        ))}
      </div>
      <div className="mt-3 shrink-0">
        <NewGoalButton onClick={onCreateGoal} />
      </div>
    </aside>
  );
}
