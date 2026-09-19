import { useState } from "react";
import type { ItemizedItem } from "../lib/api";
import { describeRowAmount, formatDate } from "../lib/format";

/**
 * Search box + filtered transaction list, shared by the sankey diagram's
 * inline panel (NetWorthFlowModal) and the standalone TransactionSearchModal
 * opened from the home page's Income/Spending tiles.
 */
export function TransactionSearch({ items, group }: { items: ItemizedItem[]; group: "income" | "spending" }) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const filtered = q
    ? items.filter((item) => (item.merchant_name ?? "").toLowerCase().includes(q) || (item.category ?? "").toLowerCase().includes(q))
    : items;

  return (
    <div>
      <input
        autoFocus
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={`Search ${group} by merchant or category`}
        aria-label={`Search ${group} transactions`}
        className="w-full rounded-lg border border-border bg-surface px-3.5 py-2 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-accent"
      />

      {filtered.length === 0 ? (
        <p className="mt-4 text-center text-sm text-ink-faint">
          {items.length === 0 ? "No transactions this period." : "No transactions match your search."}
        </p>
      ) : (
        <ul className="mt-3 max-h-64 space-y-1 overflow-y-auto pr-3" style={{ scrollbarGutter: "stable" }}>
          {filtered.map((item, i) => (
            <li key={i} className="flex items-center justify-between py-1.5 text-sm">
              <div className="min-w-0">
                <div className="truncate text-ink">{item.merchant_name ?? item.category ?? "Transaction"}</div>
                <div className="text-xs text-ink-faint">
                  {formatDate(item.date)} {item.category && `· ${item.category}`}
                  {item.is_pending && " · Pending"}
                  {describeRowAmount(item.amount, group).isCredit && " · Refund"}
                </div>
              </div>
              <RowAmount amount={item.amount} group={group} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RowAmount({ amount, group }: { amount: number; group: "income" | "spending" }) {
  const { text, isCredit } = describeRowAmount(amount, group);
  return <span className={`font-tabular shrink-0 pl-3 ${isCredit ? "text-positive" : "text-ink"}`}>{text}</span>;
}
