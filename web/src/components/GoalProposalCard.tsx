import { useState, type FormEvent } from "react";
import { ApiError, createGoal, type GoalProposal } from "../lib/api";
import { GOAL_TYPE_LABELS } from "../lib/format";

const GOAL_TYPES = Object.keys(GOAL_TYPE_LABELS);

const GOAL_TYPE_HINTS: Record<string, string> = {
  save_amount: "Build toward a specific number — a trip, a down payment, a cushion.",
  pay_off_debt: "Chip away at a card, loan, or line of credit with a real end date.",
  build_emergency_fund: "A rule of thumb is 3–6 months of expenses set aside.",
};

type CardStatus = "pending" | "created" | "dismissed";

export function GoalProposalCard({
  token,
  proposal,
  initialStatus = "pending",
  onCreated,
}: {
  token: string | null;
  proposal: GoalProposal;
  initialStatus?: CardStatus;
  onCreated: () => void | Promise<void>;
}) {
  const [type, setType] = useState(proposal.type);
  const [targetAmount, setTargetAmount] = useState(
    proposal.target_amount > 0 ? String(proposal.target_amount) : "",
  );
  const [targetDate, setTargetDate] = useState(proposal.target_date ?? "");
  const [status, setStatus] = useState<CardStatus>(initialStatus);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  if (status === "dismissed") return null;

  if (status === "created") {
    return (
      <div className="max-w-[85%] rounded-xl border border-border bg-surface p-4">
        <p className="text-sm text-ink-soft">Goal set — it’s on the left.</p>
      </div>
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    const amount = Number(targetAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Enter a target amount greater than $0.");
      return;
    }
    setError(null);
    setIsBusy(true);
    try {
      await createGoal(token, {
        type,
        target_amount: amount,
        target_date: targetDate || null,
      });
      setStatus("created");
      await onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your goal. Try again.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-[85%] space-y-3 rounded-xl border border-border bg-surface p-4">
      <div>
        <p className="text-sm font-medium text-ink">Create this goal?</p>
        <p className="mt-0.5 text-xs text-ink-faint">
          {proposal.at_limit
            ? "You already have 5 goals — finish or drop one before adding another."
            : "It will show up on the left alongside any goals you already have."}
        </p>
      </div>

      <div className="space-y-2">
        {GOAL_TYPES.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setType(t)}
            className={`w-full rounded-lg border p-3 text-left transition-colors cursor-pointer ${
              type === t ? "border-accent bg-accent-soft" : "border-border bg-bg hover:border-ink-faint"
            }`}
          >
            <div className="text-sm font-medium text-ink">{GOAL_TYPE_LABELS[t]}</div>
            <div className="mt-0.5 text-xs text-ink-soft">{GOAL_TYPE_HINTS[t]}</div>
          </button>
        ))}
      </div>

      <div>
        <label htmlFor={`proposal-amount-${proposal.target_amount}`} className="mb-1 block text-xs font-medium text-ink-soft">
          Target amount
        </label>
        <div className="flex items-center rounded-lg border border-border bg-bg px-3 focus-within:border-accent">
          <span className="font-tabular text-ink-faint">$</span>
          <input
            id={`proposal-amount-${proposal.target_amount}`}
            type="number"
            min="1"
            step="0.01"
            required
            value={targetAmount}
            onChange={(e) => setTargetAmount(e.target.value)}
            className="w-full bg-transparent py-2 pl-1.5 font-tabular text-sm text-ink outline-none"
          />
        </div>
      </div>

      <div>
        <label htmlFor={`proposal-date-${proposal.target_amount}`} className="mb-1 block text-xs font-medium text-ink-soft">
          Target date <span className="text-ink-faint">(optional)</span>
        </label>
        <input
          id={`proposal-date-${proposal.target_amount}`}
          type="date"
          value={targetDate}
          onChange={(e) => setTargetDate(e.target.value)}
          className="w-full rounded-lg border border-border bg-bg px-3 py-2 font-tabular text-sm text-ink outline-none focus:border-accent"
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setStatus("dismissed")}
          className="flex-1 rounded-lg border border-border py-2 text-sm text-ink-soft transition-colors hover:border-ink-faint hover:text-ink cursor-pointer"
        >
          Not now
        </button>
        <button
          type="submit"
          disabled={isBusy || Boolean(proposal.at_limit)}
          className="flex-1 rounded-lg bg-accent py-2 text-sm font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-60 cursor-pointer"
        >
          {isBusy ? "Saving…" : "Set goal"}
        </button>
      </div>
    </form>
  );
}
