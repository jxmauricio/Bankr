import { useState } from "react";
import { ApiError, setTransactionSplits, type CategoryNode, type TransactionRow } from "../lib/api";
import { formatMoney } from "../lib/format";
import { CategorySelect } from "./CategorySelect";

interface Part {
  amount: string;
  categoryId: string;
  note: string;
}

const cents = (s: string) => Math.round((parseFloat(s) || 0) * 100);

/**
 * Split one bank charge across categories. Amounts are typed as positive
 * sizes; the transaction's sign is applied on save. Must add up exactly.
 */
export function SplitEditor({
  token,
  txn,
  categories,
  onSaved,
  onCancel,
}: {
  token: string;
  txn: TransactionRow;
  categories: CategoryNode[];
  onSaved: (row: Omit<TransactionRow, "account">) => void;
  onCancel: () => void;
}) {
  const size = Math.abs(txn.amount);
  const sign = txn.amount < 0 ? -1 : 1;
  const [parts, setParts] = useState<Part[]>(() =>
    txn.splits.length
      ? txn.splits.map((s) => ({ amount: Math.abs(s.amount).toFixed(2), categoryId: s.category_id ?? "", note: s.notes ?? "" }))
      : [
          { amount: size.toFixed(2), categoryId: txn.category_id ?? "", note: "" },
          { amount: "", categoryId: "", note: "" },
        ],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remaining = Math.round(size * 100) - parts.reduce((s, p) => s + cents(p.amount), 0);
  const valid = remaining === 0 && parts.every((p) => cents(p.amount) > 0 && p.categoryId);

  function update(i: number, patch: Partial<Part>) {
    setParts((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  }

  async function save(next: Part[]) {
    setBusy(true);
    setError(null);
    try {
      const row = await setTransactionSplits(
        token,
        txn.id,
        next.map((p) => ({ amount: (sign * cents(p.amount)) / 100, category_id: p.categoryId, note: p.note || undefined })),
      );
      onSaved(row);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the split. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-[18px] bg-surface p-4" aria-label="Split transaction">
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] font-semibold text-ink">Split {formatMoney(size)}</span>
        <span className={`font-tabular text-xs ${remaining === 0 ? "text-ink-faint" : "text-warn"}`}>
          {remaining === 0 ? "Adds up" : remaining > 0 ? `${formatMoney(remaining / 100)} left` : `${formatMoney(-remaining / 100)} over`}
        </span>
      </div>
      {parts.map((p, i) => (
        <div key={i} className="flex flex-col gap-1.5 border-t border-line pt-3 first-of-type:border-0 first-of-type:pt-0">
          <div className="flex gap-2">
            <label className="flex h-10 w-[104px] shrink-0 items-center gap-1 rounded-xl border border-line bg-raised px-2.5 focus-within:border-signal">
              <span className="text-[13px] text-ink-faint">$</span>
              <input
                inputMode="decimal"
                aria-label={`Split ${i + 1} amount`}
                value={p.amount}
                onChange={(e) => update(i, { amount: e.target.value.replace(/[^0-9.]/g, "") })}
                className="w-full min-w-0 bg-transparent font-tabular text-[13px] text-ink outline-none"
              />
            </label>
            <CategorySelect
              label={`Split ${i + 1} category`}
              categories={categories}
              value={p.categoryId}
              onChange={(id) => update(i, { categoryId: id })}
              className="flex-1"
            />
            {parts.length > 2 && (
              <button
                type="button"
                aria-label={`Remove split ${i + 1}`}
                onClick={() => setParts((ps) => ps.filter((_, j) => j !== i))}
                className="h-10 w-10 shrink-0 cursor-pointer rounded-xl text-ink-faint hover:text-ink"
              >
                ✕
              </button>
            )}
          </div>
          <input
            aria-label={`Split ${i + 1} note`}
            placeholder="Note (optional)"
            value={p.note}
            maxLength={200}
            onChange={(e) => update(i, { note: e.target.value })}
            className="h-9 rounded-xl border border-line bg-transparent px-2.5 text-xs text-ink outline-none placeholder:text-ink-faint focus:border-signal"
          />
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        {parts.length < 10 && (
          <button
            type="button"
            onClick={() =>
              setParts((ps) => [...ps, { amount: remaining > 0 ? (remaining / 100).toFixed(2) : "", categoryId: "", note: "" }])
            }
            className="h-9 cursor-pointer rounded-xl bg-raised px-3 text-xs text-ink-soft hover:text-ink"
          >
            + Add split
          </button>
        )}
        {txn.is_split && (
          <button
            type="button"
            disabled={busy}
            onClick={() => save([])}
            className="h-9 cursor-pointer rounded-xl bg-raised px-3 text-xs text-ink-soft hover:text-negative"
          >
            Remove split
          </button>
        )}
      </div>
      {error && <p className="m-0 text-xs text-negative">{error}</p>}
      <div className="grid grid-cols-2 gap-2">
        <button type="button" onClick={onCancel} className="h-10 cursor-pointer rounded-xl bg-raised text-[13px] text-ink">
          Cancel
        </button>
        <button
          type="button"
          disabled={!valid || busy}
          onClick={() => save(parts)}
          className="h-10 cursor-pointer rounded-xl bg-signal text-[13px] font-semibold text-bg hover:bg-signal-hi disabled:cursor-default disabled:opacity-40"
        >
          {busy ? "Saving…" : "Save split"}
        </button>
      </div>
    </section>
  );
}
