import { BudgetSection } from "../components/BudgetSection";
import { RecurringSection } from "../components/RecurringSection";

/** Plan: what's coming up and what's left to spend this month. */
export function PlanView({
  token,
  refreshKey,
  focus,
  onChanged,
}: {
  token: string;
  refreshKey?: unknown;
  /** Budget or recurring changed; other surfaces may show it. */
  onChanged?: () => void;
  /** Section to scroll to on open. */
  focus?: "budget" | "recurring" | null;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto animate-view">
      <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-4 px-4 py-4 lg:px-8 lg:py-6">
        <div className="flex flex-col gap-1">
          <h1 className="m-0 text-[22px] font-semibold tracking-[-0.02em] text-ink lg:text-[26px]">Plan</h1>
          <span className="text-[13px] text-ink-soft">Your budget for the month and the bills on the way.</span>
        </div>
        <BudgetSection token={token} refreshKey={refreshKey} focus={focus === "budget"} onChanged={onChanged} />
        <RecurringSection token={token} refreshKey={refreshKey} focus={focus === "recurring"} onChanged={onChanged} />
      </div>
    </div>
  );
}
