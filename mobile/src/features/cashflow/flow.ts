// Ported from web/src/pages/CashFlowView.tsx (sides and its node types).
import type { CashFlowBreakdown } from "@/lib/api";
import { useColors } from "@/theme/theme";

export const MAX_CATEGORIES = 8;

export type Kind = "income" | "deficit" | "spend" | "transfer" | "kept";

/** Where tapping a node goes in Transactions. */
export interface FlowTarget {
  category: string | null;
  query: string;
}

export interface FlowNode {
  name: string;
  amount: number;
  kind: Kind;
  target?: FlowTarget;
}

/** Each kind's color in the current appearance. */
export function useKindColors(): Record<Kind, string> {
  const colors = useColors();
  return {
  income: colors.accent,
  deficit: colors.warn,
  spend: colors.spend,
  transfer: colors.inkSoft,
  kept: colors.positive,
  };
}

export const whole = (n: number) => "$" + Math.round(n).toLocaleString("en-US");

/** Income and transfers in on the left; spending, transfers out, and leftover on the right. Both sides sum to the same total. */
export function sides(flow: CashFlowBreakdown): { left: FlowNode[]; right: FlowNode[]; total: number } {
  const transferIn = flow.transfer_in ?? 0;
  const transferOut = flow.transfer_out ?? 0;
  const moneyIn = flow.income + transferIn;
  const moneyOut = flow.spending + transferOut;

  const left: FlowNode[] = flow.sources.map((s) => ({
    name: s.name,
    amount: s.amount,
    kind: "income",
    // "N other sources" is a roll-up, so it lists every income row.
    target: { category: "Income", query: /^\d+ other sources$/.test(s.name) ? "" : s.name },
  }));
  for (const t of flow.transfers_in ?? []) {
    left.push({
      name: t.name,
      amount: t.amount,
      kind: "transfer",
      target: { category: "Transfer", query: /^\d+ other /.test(t.name) ? "" : t.name },
    });
  }
  if (moneyOut > moneyIn) {
    left.push({ name: "From your balances", amount: moneyOut - moneyIn, kind: "deficit" });
  }

  const cats = flow.categories;
  const shown = cats.length > MAX_CATEGORIES ? cats.slice(0, MAX_CATEGORIES - 1) : cats;
  const right: FlowNode[] = shown.map((c) => ({ name: c.name, amount: c.amount, kind: "spend", target: { category: c.name, query: "" } }));
  if (cats.length > shown.length) {
    // A roll-up of several categories has no single filter to open.
    const tail = cats.slice(shown.length);
    right.push({ name: `${tail.length} more`, amount: tail.reduce((s, c) => s + c.amount, 0), kind: "spend" });
  }
  for (const t of flow.transfers_out ?? []) {
    right.push({
      name: t.name,
      amount: t.amount,
      kind: "transfer",
      target: { category: "Transfer", query: /^\d+ other /.test(t.name) ? "" : t.name },
    });
  }
  if (flow.net > 0) right.push({ name: "Left over", amount: flow.net, kind: "kept" });

  return { left, right, total: Math.max(moneyIn, moneyOut) };
}
