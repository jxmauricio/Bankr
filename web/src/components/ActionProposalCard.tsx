import { useState, type ReactNode } from "react";
import { ApiError, createRule, moveBudgetMoney, type ActionProposal } from "../lib/api";
import { formatMoney } from "../lib/format";

type Status = "pending" | "busy" | "done" | "dismissed";

/**
 * A change the assistant drafted in chat (a rule, a budget move). Nothing
 * happens until the user taps Confirm.
 */
export function ActionProposalCard({
  token,
  proposal,
  onDone,
}: {
  token: string | null;
  proposal: ActionProposal;
  onDone: () => void | Promise<void>;
}) {
  const [status, setStatus] = useState<Status>("pending");
  const [error, setError] = useState<string | null>(null);

  const { eyebrow, title, detail, confirm, done } = describe(proposal);

  if (status === "dismissed") return null;
  if (status === "done") {
    return (
      <div className="w-full rounded-[20px] bg-surface p-4">
        <p className="m-0 text-sm text-signal">✓ {done}</p>
      </div>
    );
  }

  async function accept() {
    if (!token) return;
    setStatus("busy");
    setError(null);
    try {
      await perform(token, proposal);
      setStatus("done");
      await onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't do that. Try again.");
      setStatus("pending");
    }
  }

  return (
    <div className="flex w-full flex-col gap-3 rounded-[20px] border border-signal/35 bg-signal-wash p-5">
      <div>
        <p className="m-0 font-mono text-[11px] tracking-[0.12em] text-signal">{eyebrow}</p>
        <p className="m-0 mt-1.5 text-[15px] font-semibold text-ink">{title}</p>
        {detail && <p className="m-0 mt-0.5 text-xs text-ink-soft">{detail}</p>}
      </div>
      {error && <p className="m-0 text-xs text-negative">{error}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={accept}
          disabled={status === "busy" || !token}
          className="h-11 flex-1 cursor-pointer rounded-[14px] bg-signal text-sm font-semibold text-bg hover:bg-signal-hi disabled:opacity-60"
        >
          {status === "busy" ? "Saving…" : confirm}
        </button>
        <button
          type="button"
          onClick={() => setStatus("dismissed")}
          className="h-11 cursor-pointer rounded-[14px] px-4 text-sm text-ink-soft hover:text-ink"
        >
          Not now
        </button>
      </div>
    </div>
  );
}

function describe(p: ActionProposal): { eyebrow: string; title: ReactNode; detail: string | null; confirm: string; done: string } {
  switch (p.kind) {
    case "rule":
      return {
        eyebrow: "MAKE THIS A RULE?",
        title: (
          <>
            Always put “{p.merchant_contains}” in {p.category}
          </>
        ),
        detail: [
          p.set_merchant_name ? `Shown as ${p.set_merchant_name}.` : null,
          p.would_change ? `Also updates ${p.would_change} past transaction${p.would_change === 1 ? "" : "s"}.` : null,
        ]
          .filter(Boolean)
          .join(" ") || null,
        confirm: "Make rule",
        done: `Rule saved — “${p.merchant_contains}” now goes to ${p.category}.`,
      };
    case "budget_move":
      return {
        eyebrow: "MOVE BUDGET MONEY?",
        title: (
          <>
            Move {formatMoney(p.amount)} from {p.from_name} to {p.to_name}
          </>
        ),
        detail: `For ${p.month}. ${p.from_name} will have that much less to spend.`,
        confirm: "Move it",
        done: `Moved ${formatMoney(p.amount)} to ${p.to_name}.`,
      };
  }
}

async function perform(token: string, p: ActionProposal): Promise<void> {
  switch (p.kind) {
    case "rule":
      await createRule(token, {
        merchant_contains: p.merchant_contains,
        set_category_id: p.category_id,
        set_merchant_name: p.set_merchant_name ?? undefined,
        apply_to_existing: true,
      });
      return;
    case "budget_move":
      await moveBudgetMoney(token, { month: p.month, from_key: p.from_key, to_key: p.to_key, amount: p.amount });
  }
}
