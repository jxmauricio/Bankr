import { useState, type FormEvent } from "react";
import { ApiError, createGoal } from "../lib/api";
import { useSession } from "../lib/session";
import { GOAL_TYPE_LABELS } from "../lib/format";

const GOAL_TYPES = Object.keys(GOAL_TYPE_LABELS) as (keyof typeof GOAL_TYPE_LABELS)[];

const GOAL_TYPE_HINTS: Record<string, string> = {
  save_amount: "Build toward a specific number — a trip, a down payment, a cushion.",
  pay_off_debt: "Chip away at a card, loan, or line of credit with a real end date.",
  build_emergency_fund: "A rule of thumb is 3–6 months of expenses set aside.",
};

export function GoalSetupPage({ onGoalSet }: { onGoalSet: () => void }) {
  const { token } = useSession();
  const [type, setType] = useState<string | null>(null);
  const [targetAmount, setTargetAmount] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !type) return;
    const amount = Number(targetAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Enter a target amount greater than $0.");
      return;
    }
    setError(null);
    setIsBusy(true);
    try {
      await createGoal(token, { type, target_amount: amount, target_date: targetDate || null });
      onGoalSet();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your goal. Try again.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="font-display text-2xl font-semibold text-ink">What's your goal?</h1>
          <p className="mt-2 text-ink-soft">Pick one to start — you can always change it later.</p>
        </div>

        <div className="space-y-2.5">
          {GOAL_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setType(t)}
              className={`w-full rounded-xl border p-4 text-left transition-colors cursor-pointer ${
                type === t ? "border-accent bg-accent-soft" : "border-border bg-surface hover:border-ink-faint"
              }`}
            >
              <div className="font-medium text-ink">{GOAL_TYPE_LABELS[t]}</div>
              <div className="mt-0.5 text-sm text-ink-soft">{GOAL_TYPE_HINTS[t]}</div>
            </button>
          ))}
        </div>

        {type && (
          <form onSubmit={handleSubmit} className="mt-6 space-y-4 rounded-xl border border-border bg-surface p-4">
            <div>
              <label htmlFor="amount" className="mb-1.5 block text-sm font-medium text-ink-soft">
                Target amount
              </label>
              <div className="flex items-center rounded-lg border border-border bg-white px-3 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent-soft">
                <span className="font-tabular text-ink-faint">$</span>
                <input
                  id="amount"
                  type="number"
                  min="1"
                  step="0.01"
                  required
                  value={targetAmount}
                  onChange={(e) => setTargetAmount(e.target.value)}
                  className="w-full bg-transparent py-2 pl-1.5 font-tabular text-ink outline-none"
                  placeholder="6,000"
                />
              </div>
            </div>
            <div>
              <label htmlFor="date" className="mb-1.5 block text-sm font-medium text-ink-soft">
                Target date <span className="text-ink-faint">(optional)</span>
              </label>
              <input
                id="date"
                type="date"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
                className="w-full rounded-lg border border-border bg-white px-3 py-2 font-tabular text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft"
              />
            </div>

            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={isBusy}
              className="w-full rounded-lg bg-accent py-2.5 font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-60 cursor-pointer"
            >
              {isBusy ? "Saving…" : "Set goal"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
