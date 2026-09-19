import { useState } from "react";
import { ApiError, createGoal, type GoalProposal } from "../lib/api";
import { GOAL_TYPE_LABELS } from "../lib/format";
import { formatMoney } from "../lib/format";

/**
 * Shown under an assistant reply when the agent has drafted a goal via the
 * propose_goal tool. Bankr never creates the Goal row itself -- this card is
 * the only path from a chat proposal to an actual POST /goals.
 */
export function GoalProposalCard({
  token,
  proposal,
  onCreated,
}: {
  token: string | null;
  proposal: GoalProposal;
  onCreated: () => void | Promise<void>;
}) {
  const [status, setStatus] = useState<"idle" | "saving" | "done">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    if (!token || proposal.at_limit) return;
    setError(null);
    setStatus("saving");
    try {
      await createGoal(token, {
        type: proposal.type,
        target_amount: proposal.target_amount,
        target_date: proposal.target_date,
      });
      setStatus("done");
      await onCreated();
    } catch (err) {
      setStatus("idle");
      setError(err instanceof ApiError ? err.message : "Couldn't save that goal. Try again.");
    }
  }

  return (
    <div className="w-full max-w-[85%] rounded-xl border border-gold bg-gold-soft/40 p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-gold-strong">
        {status === "done" ? "Goal set" : "Suggested goal"}
      </div>
      <div className="mt-1.5 font-medium text-ink">{GOAL_TYPE_LABELS[proposal.type] ?? proposal.type}</div>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className="font-tabular text-lg font-semibold text-ink">{formatMoney(proposal.target_amount)}</span>
        {proposal.target_date && <span className="text-sm text-ink-faint">by {proposal.target_date}</span>}
      </div>

      {proposal.at_limit ? (
        <p className="mt-3 text-sm text-ink-faint">
          You already have {proposal.active_count} active goals, the max Bankr tracks at once. Finish or drop one
          first.
        </p>
      ) : (
        <>
          {error && (
            <p role="alert" className="mt-2 text-sm text-danger">
              {error}
            </p>
          )}
          <button
            type="button"
            onClick={handleConfirm}
            disabled={status !== "idle"}
            className="mt-3 rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-60 cursor-pointer"
          >
            {status === "saving" ? "Setting…" : status === "done" ? "Set ✓" : "Set goal"}
          </button>
        </>
      )}
    </div>
  );
}
