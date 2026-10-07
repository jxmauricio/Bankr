import { useState, type ReactNode } from "react";
import { ApiError, updateTransaction, type CategoryNode, type TransactionEdit, type TransactionRow } from "../lib/api";
import { formatMoney } from "../lib/format";
import { CategorySelect } from "./CategorySelect";
import { SplitEditor } from "./SplitEditor";

type EditedRow = Omit<TransactionRow, "account">;

/**
 * The editable part of the transaction drawer: category, name, note,
 * exclude, split. Each change saves on its own; nothing waits for a Save.
 */
export function TransactionEditor({
  token,
  txn,
  categories,
  onUpdated,
  children,
}: {
  token: string;
  txn: TransactionRow;
  categories: CategoryNode[];
  onUpdated: (row: EditedRow) => void;
  /** Shown under the category picker, e.g. the "make this a rule" offer. */
  children?: (afterCategoryChange: string | null) => ReactNode;
}) {
  const [splitting, setSplitting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [changedTo, setChangedTo] = useState<string | null>(null);

  async function save(edit: TransactionEdit) {
    setBusy(true);
    setError(null);
    try {
      onUpdated(await updateTransaction(token, txn.id, edit));
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that change. Try again.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (splitting) {
    return (
      <SplitEditor
        token={token}
        txn={txn}
        categories={categories}
        onCancel={() => setSplitting(false)}
        onSaved={(row) => {
          onUpdated(row);
          setSplitting(false);
        }}
      />
    );
  }

  return (
    <section className="flex flex-col gap-3 rounded-[18px] bg-surface p-4" aria-label="Edit transaction">
      {txn.is_split ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] text-ink-soft">Split across</span>
          {txn.splits.map((s) => (
            <div key={s.id} className="flex justify-between gap-3 text-[13px]">
              <span className="truncate text-ink">
                {s.parent_category ? `${s.category} · ${s.parent_category}` : s.category}
                {s.notes && <span className="text-ink-faint"> — {s.notes}</span>}
              </span>
              <span className="shrink-0 font-tabular text-xs text-ink-soft">{formatMoney(Math.abs(s.amount))}</span>
            </div>
          ))}
        </div>
      ) : (
        <Row label="Category">
          <CategorySelect
            label="Category"
            categories={categories}
            value={txn.category_id ?? ""}
            disabled={busy}
            onChange={async (id) => {
              if (await save({ category_id: id })) setChangedTo(id);
            }}
            className="w-[60%]"
          />
        </Row>
      )}
      {children?.(changedTo)}

      <Row label="Name">
        <TextField
          key={`${txn.id}-name`}
          label="Merchant name"
          initial={txn.merchant_name ?? ""}
          placeholder={txn.original_merchant_name ?? "Merchant"}
          disabled={busy}
          onCommit={(v) => v !== (txn.merchant_name ?? "") && save({ merchant_name: v })}
        />
      </Row>
      {txn.original_merchant_name && txn.merchant_name !== txn.original_merchant_name && (
        <span className="-mt-1.5 text-right text-xs text-ink-faint">Bank calls it “{txn.original_merchant_name}”</span>
      )}

      <Row label="Note">
        <TextField
          key={`${txn.id}-note`}
          label="Note"
          initial={txn.notes ?? ""}
          placeholder="Add a note"
          disabled={busy}
          onCommit={(v) => v !== (txn.notes ?? "") && save({ notes: v })}
        />
      </Row>

      <label className="flex min-h-11 cursor-pointer items-center justify-between gap-3">
        <span className="flex flex-col">
          <span className="text-[13px] text-ink">Exclude from totals</span>
          <span className="text-xs text-ink-faint">Won't count toward spending, income or budgets.</span>
        </span>
        <input
          type="checkbox"
          checked={txn.is_excluded}
          disabled={busy}
          onChange={(e) => save({ excluded: e.target.checked })}
          className="h-5 w-5 cursor-pointer accent-[var(--color-signal)]"
        />
      </label>

      <button
        type="button"
        onClick={() => {
          setChangedTo(null); // the rule offer was about the old single category
          setSplitting(true);
        }}
        className="h-10 cursor-pointer rounded-xl bg-raised text-[13px] text-ink hover:text-signal-hi"
      >
        {txn.is_split ? "Edit split" : "Split across categories"}
      </button>
      {error && <p className="m-0 text-xs text-negative">{error}</p>}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[13px] text-ink-soft">{label}</span>
      {children}
    </div>
  );
}

/** Saves on blur or Enter; Esc reverts. */
function TextField({
  label,
  initial,
  placeholder,
  disabled,
  onCommit,
}: {
  label: string;
  initial: string;
  placeholder: string;
  disabled?: boolean;
  onCommit: (value: string) => unknown;
}) {
  const [value, setValue] = useState(initial);
  return (
    <input
      aria-label={label}
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      maxLength={120}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => onCommit(value.trim())}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          e.stopPropagation();
          setValue(initial);
        }
      }}
      className="h-10 w-[60%] min-w-0 rounded-xl border border-line bg-raised px-2.5 text-[13px] text-ink outline-none placeholder:text-ink-faint focus:border-signal"
    />
  );
}
