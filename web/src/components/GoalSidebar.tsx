import type { GoalProgress } from "../lib/api";
import { GoalPaceTrack } from "./GoalPaceTrack";

/**
 * Fills the empty gutter beside the centered chat column on wide screens
 * with goal progress. Hidden below `lg` since there's no spare space to put
 * it in on narrower viewports.
 */
export function GoalSidebar({ goals }: { goals: GoalProgress[] }) {
  return (
    <aside className="hidden w-72 shrink-0 flex-col gap-3 overflow-y-auto border-r border-border p-5 lg:flex">
      {goals.length > 0 ? (
        goals.map((goal) => <GoalPaceTrack key={goal.id} progress={goal} />)
      ) : (
        <div className="rounded-xl border border-border bg-surface p-4 text-sm text-ink-faint">
          No goal set yet.
        </div>
      )}
    </aside>
  );
}
