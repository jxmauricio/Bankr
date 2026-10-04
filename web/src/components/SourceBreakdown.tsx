import { useEffect, useMemo, useState } from "react";
import { fetchSpending, type ItemizedTransactions, type SourceQuery } from "../lib/api";
import { formatMoney } from "../lib/format";

const BAR_COLORS = ["var(--color-signal)", "var(--color-warn)", "var(--color-ink-soft)", "var(--color-signal-hi)"];

/** A compact "where it went" card under an answer: the transactions behind a
 * source chip, grouped by merchant, with each merchant's share of the total.
 * Everything here is fetched from the same query the chip opens, so the numbers
 * match the drill-down exactly. */
export function SourceBreakdown({
  token,
  query,
  onOpen,
}: {
  token: string | null;
  query: SourceQuery;
  onOpen: (query: SourceQuery) => void;
}) {
  const [result, setResult] = useState<ItemizedTransactions | null>(null);

  useEffect(() => {
    if (!token) return;
    let stale = false;
    fetchSpending(token, query)
      .then((r) => !stale && setResult(r))
      .catch(() => !stale && setResult(null));
    return () => {
      stale = true;
    };
  }, [token, query]);

  const rows = useMemo(() => {
    if (!result) return [];
    const byMerchant = new Map<string, { name: string; visits: number; total: number }>();
    for (const item of result.items) {
      const name = item.merchant_name ?? item.category ?? "Other";
      const row = byMerchant.get(name) ?? { name, visits: 0, total: 0 };
      row.visits += 1;
      row.total += Math.abs(item.amount);
      byMerchant.set(name, row);
    }
    return [...byMerchant.values()].sort((a, b) => b.total - a.total);
  }, [result]);

  if (!result || result.items.length < 2 || rows.length < 2) return null;

  const keep = rows.length === 5 ? 5 : 4;
  const top = rows.slice(0, keep);
  const rest = rows.slice(keep);
  const restTotal = rest.reduce((n, r) => n + r.total, 0);
  const shown = restTotal > 0 ? [...top, { name: `${rest.length} more`, visits: rest.reduce((n, r) => n + r.visits, 0), total: restTotal }] : top;
  const total = shown.reduce((n, r) => n + r.total, 0);

  return (
    <div className="flex w-full flex-col gap-3 rounded-2xl bg-raised p-4">
      <div className="flex justify-between text-xs text-ink-soft">
        <span>
          {result.category ?? "Spending"} · {result.label}
        </span>
        <span className="font-mono tabular-nums">{formatMoney(Math.abs(result.total))}</span>
      </div>
      <div
        role="img"
        aria-label={shown.map((r) => `${r.name} ${Math.round((r.total / total) * 100)}%`).join(", ")}
        className="flex h-2 gap-0.5 overflow-hidden rounded"
      >
        {shown.map((r, i) => (
          <div key={r.name} style={{ width: `${(r.total / total) * 100}%`, background: BAR_COLORS[i % BAR_COLORS.length] }} />
        ))}
      </div>
      <table className="w-full border-collapse text-[13px]">
        <tbody>
          {shown.map((r, i) => (
            <tr key={r.name} className="border-t border-line">
              <td className="py-2">
                <span className="flex items-center gap-2">
                  <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: BAR_COLORS[i % BAR_COLORS.length] }} />
                  <span className="truncate">{r.name}</span>
                </span>
              </td>
              <td className="py-2 text-xs text-ink-faint">
                {r.visits} {r.visits === 1 ? "visit" : "visits"}
              </td>
              <td className="py-2 text-right font-mono tabular-nums">{formatMoney(r.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={() => onOpen(query)}
        className="self-start text-xs text-signal underline decoration-dotted underline-offset-4 hover:text-signal-hi cursor-pointer"
      >
        See all {result.transaction_count} transactions
      </button>
    </div>
  );
}
