import { useEffect, useState } from "react";
import { fetchIncome, fetchSpending, type ItemizedItem } from "../lib/api";
import { TransactionSearch } from "./TransactionSearch";

type Period = "week" | "month" | "year";

/**
 * Standalone modal opened from the home page's Income/Spending stat tiles —
 * distinct from NetWorthFlowModal's inline search panel, which only opens
 * from clicking those groups inside the sankey diagram.
 */
export function TransactionSearchModal({
  token,
  group,
  onClose,
}: {
  token: string;
  group: "income" | "spending";
  onClose: () => void;
}) {
  const [period, setPeriod] = useState<Period>("month");
  const [items, setItems] = useState<ItemizedItem[] | null>(null);

  useEffect(() => {
    const fetchItems = group === "income" ? fetchIncome : fetchSpending;
    fetchItems(token, period).then((r) => setItems(r.items));
  }, [token, group, period]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-border bg-surface p-6"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`${group === "income" ? "Income" : "Spending"} transactions`}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-display text-lg font-semibold capitalize text-ink">{group} transactions</h2>
            <div className="mt-2 inline-flex rounded-full border border-border bg-bg p-0.5 text-xs">
              {(["week", "month", "year"] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPeriod(p)}
                  className={`rounded-full px-2.5 py-1 capitalize transition-colors cursor-pointer ${
                    period === p ? "bg-accent text-white" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-1.5 text-ink-soft transition-colors hover:bg-bg hover:text-ink cursor-pointer"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="mt-4">
          {items === null ? (
            <div className="flex h-32 items-center justify-center text-sm text-ink-faint">Loading…</div>
          ) : (
            <TransactionSearch items={items} group={group} />
          )}
        </div>
      </div>
    </div>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" />
    </svg>
  );
}
