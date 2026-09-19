import { useEffect, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { sankey, type SankeyNode } from "d3-sankey";
import { fetchIncome, fetchNetWorth, fetchSpending, type ItemizedItem, type NetWorthHistory } from "../lib/api";
import { formatMoney } from "../lib/format";
import { TransactionSearch } from "./TransactionSearch";

type FlowGroup = "income" | "spending";

/**
 * Fixed category -> color slot order, matching seed_categories.py's
 * DEFAULT_CATEGORIES. Fixed (not cycled per-render) so a category's color
 * is stable across opens, per the dataviz rule "color follows the entity."
 * Palette is the validated dark-mode categorical set (8 hues, ΔE-checked
 * against this app's #10131C surface).
 */
const CATEGORY_ORDER = [
  "Income",
  "Groceries",
  "Dining",
  "Transportation",
  "Rent & Housing",
  "Utilities",
  "Subscriptions",
  "Entertainment",
  "Shopping",
  "Health",
  "Transfer",
  "Other",
];
const CATEGORY_PALETTE = [
  "#3987e5",
  "#d95926",
  "#199e70",
  "#c98500",
  "#d55181",
  "#008300",
  "#9085e9",
  "#e66767",
];

function colorForCategory(name: string): string {
  const i = CATEGORY_ORDER.indexOf(name);
  return i === -1 ? "#565D72" : CATEGORY_PALETTE[i % CATEGORY_PALETTE.length];
}

interface CategorySlice {
  name: string;
  amount: number;
}

function aggregateByCategory(items: ItemizedItem[], group: "income" | "spending"): CategorySlice[] {
  // Sign-aware: spending rows are negative, so a refund (positive) nets a
  // category down instead of being added to it. Floored at zero like the
  // backend's totals (app/services/money_query.py spend_query).
  const totals = new Map<string, number>();
  for (const item of items) {
    const key = item.category ?? "Uncategorized";
    const amount = group === "spending" ? -item.amount : item.amount;
    totals.set(key, (totals.get(key) ?? 0) + amount);
  }
  return [...totals.entries()]
    .filter(([, amount]) => amount > 0)
    .map(([name, amount]) => ({ name, amount }))
    .sort((a, b) => b.amount - a.amount);
}

const HEIGHT = 320;
const NODE_WIDTH = 6;
const NODE_GAP = 3;
const INCOME_SPENDING_GAP = 28;
const LABEL_GAP = 8;
// Left margin reserves room for the root node's own label (it has no
// incoming ribbon to carry it); the two inter-column gaps reserve room for
// every other label, which rides on its node's incoming ribbon instead of
// sitting in a box — long "Category: $12,345.67" strings need more room
// than the "Income: $..." / "Spending: $..." labels in the first gap.
const MARGIN_LEFT = 150;
const GAP_1_2 = 160;
const GAP_2_3 = 190;
const RIGHT_PAD = 20;

const COL1_X = [MARGIN_LEFT, MARGIN_LEFT + NODE_WIDTH] as const;
const COL2_X = [COL1_X[1] + GAP_1_2, COL1_X[1] + GAP_1_2 + NODE_WIDTH] as const;
const COL3_X = [COL2_X[1] + GAP_2_3, COL2_X[1] + GAP_2_3 + NODE_WIDTH] as const;
const COLUMN_X = [COL1_X, COL2_X, COL3_X] as const;
const WIDTH = COL3_X[1] + RIGHT_PAD;

function ribbonPath(x0: number, y0Top: number, y0Bot: number, x1: number, y1Top: number, y1Bot: number): string {
  const xMid = (x0 + x1) / 2;
  return `M${x0},${y0Top} C${xMid},${y0Top} ${xMid},${y1Top} ${x1},${y1Top} L${x1},${y1Bot} C${xMid},${y1Bot} ${xMid},${y0Bot} ${x0},${y0Bot} Z`;
}

interface FlowNodeDatum {
  id: string;
  name: string;
  amount: number;
  color: string;
}

interface FlowLinkDatum {
  source: string;
  target: string;
  value: number;
  color: string;
}

type LayoutNode = SankeyNode<FlowNodeDatum, FlowLinkDatum>;

/**
 * Builds the net-worth -> income/spending -> category graph and lays it out
 * with d3-sankey (node/link value math + vertical stacking). Column x-ranges
 * stay fixed to COLUMN_X rather than d3's default even spacing, since d3-sankey
 * only uses x to determine column order/depth, not the vertical (value-based)
 * layout — overriding x after layout is safe.
 */
function layoutFlow(income: CategorySlice[], spending: CategorySlice[], totalIncome: number, totalSpending: number) {
  const nodes: FlowNodeDatum[] = [
    { id: "networth", name: "Net worth", amount: totalIncome + totalSpending, color: "var(--color-gold)" },
  ];
  const links: FlowLinkDatum[] = [];

  if (totalIncome > 0) {
    nodes.push({ id: "income", name: "Income", amount: totalIncome, color: "var(--color-positive)" });
    links.push({ source: "networth", target: "income", value: totalIncome, color: "var(--color-positive)" });
    for (const slice of income) {
      nodes.push({ id: `inc:${slice.name}`, name: slice.name, amount: slice.amount, color: colorForCategory(slice.name) });
      links.push({ source: "income", target: `inc:${slice.name}`, value: slice.amount, color: colorForCategory(slice.name) });
    }
  }
  if (totalSpending > 0) {
    nodes.push({ id: "spending", name: "Spending", amount: totalSpending, color: "var(--color-danger)" });
    links.push({ source: "networth", target: "spending", value: totalSpending, color: "var(--color-danger)" });
    for (const slice of spending) {
      nodes.push({ id: `sp:${slice.name}`, name: slice.name, amount: slice.amount, color: colorForCategory(slice.name) });
      links.push({ source: "spending", target: `sp:${slice.name}`, value: slice.amount, color: colorForCategory(slice.name) });
    }
  }

  // Reserve INCOME_SPENDING_GAP of vertical room (when both groups are
  // present) so it can be spliced in below, between the income and spending
  // subtrees, without pushing the diagram past HEIGHT.
  const extraGap = totalIncome > 0 && totalSpending > 0 ? INCOME_SPENDING_GAP : 0;

  const layout = sankey<FlowNodeDatum, FlowLinkDatum>()
    .nodeId((d) => d.id)
    .nodeWidth(1)
    .nodePadding(NODE_GAP)
    .extent([
      [0, 0],
      [WIDTH, HEIGHT - extraGap],
    ])(
    // d3-sankey mutates its input, so hand it fresh copies
    { nodes: nodes.map((d) => ({ ...d })), links: links.map((d) => ({ ...d })) },
  );

  for (const node of layout.nodes) {
    const [x0, x1] = COLUMN_X[node.depth ?? 0];
    node.x0 = x0;
    node.x1 = x1;
  }

  if (extraGap > 0) {
    const isSpendingSide = (id: string) => id === "spending" || id.startsWith("sp:");
    for (const node of layout.nodes) {
      if (isSpendingSide(node.id)) {
        node.y0 = (node.y0 ?? 0) + extraGap;
        node.y1 = (node.y1 ?? 0) + extraGap;
      } else if (node.id === "networth") {
        // Net worth spans the whole trunk, so it grows to reach the
        // (now lower) bottom of the spending subtree.
        node.y1 = (node.y1 ?? 0) + extraGap;
      }
    }
    for (const link of layout.links) {
      const sourceId = (link.source as LayoutNode).id;
      const targetId = (link.target as LayoutNode).id;
      // A link's endpoint shifts only if the node it attaches to shifted —
      // the networth -> spending link's source stays put on the (unmoved)
      // trunk while its target moves, so the ribbon stretches to bridge the gap.
      if (isSpendingSide(sourceId)) link.y0 = (link.y0 ?? 0) + extraGap;
      if (isSpendingSide(targetId)) link.y1 = (link.y1 ?? 0) + extraGap;
    }
  }

  return layout;
}

export function NetWorthFlowModal({
  token,
  netWorth,
  onClose,
}: {
  token: string;
  netWorth: number | null;
  onClose: () => void;
}) {
  const [incomeItems, setIncomeItems] = useState<ItemizedItem[] | null>(null);
  const [spendingItems, setSpendingItems] = useState<ItemizedItem[] | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<FlowGroup | null>(null);
  const [breakdown, setBreakdown] = useState<NetWorthHistory | null>(null);

  useEffect(() => {
    fetchNetWorth(token).then(setBreakdown);
    fetchIncome(token, "month").then((r) => setIncomeItems(r.items));
    fetchSpending(token, "month").then((r) => setSpendingItems(r.items));
  }, [token]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const loading = incomeItems === null || spendingItems === null;
  const income = incomeItems ? aggregateByCategory(incomeItems, "income") : null;
  const spending = spendingItems ? aggregateByCategory(spendingItems, "spending") : null;
  const totalIncome = income?.reduce((s, c) => s + c.amount, 0) ?? 0;
  const totalSpending = spending?.reduce((s, c) => s + c.amount, 0) ?? 0;
  const grandTotal = totalIncome + totalSpending;

  function toggleGroup(group: FlowGroup) {
    setSelectedGroup((prev) => (prev === group ? null : group));
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="max-h-[90vh] w-full max-w-6xl overflow-y-auto rounded-2xl border border-border bg-surface p-8"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Net worth flow this month"
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-display text-lg font-semibold text-ink">
              Net worth {netWorth !== null ? formatMoney(netWorth) : ""}
            </h2>
            <p className="mt-1 text-sm text-ink-faint">Every linked account, added up.</p>
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

        <AccountBreakdown breakdown={breakdown} />

        <div className="mt-8 flex items-start justify-between">
          <div>
            <h2 className="font-display text-lg font-semibold text-ink">This month's flow</h2>
            <p className="mt-1 text-sm text-ink-faint">
              Net worth {netWorth !== null ? formatMoney(netWorth) : "—"} · illustrative, not a literal
              period-over-period reconciliation
            </p>
          </div>
        </div>

        {loading ? (
          <div className="mt-8 flex h-64 items-center justify-center text-sm text-ink-faint">Loading…</div>
        ) : grandTotal === 0 ? (
          <div className="mt-8 flex h-64 items-center justify-center text-sm text-ink-faint">
            No income or spending recorded this month yet.
          </div>
        ) : (
          <>
            <FlowSvg
              income={income!}
              spending={spending!}
              totalIncome={totalIncome}
              totalSpending={totalSpending}
              selectedGroup={selectedGroup}
              onSelectGroup={toggleGroup}
            />
            <FlowLegend income={income!} spending={spending!} totalIncome={totalIncome} totalSpending={totalSpending} />
            {selectedGroup && (
              <ItemSearchPanel
                key={selectedGroup}
                group={selectedGroup}
                items={(selectedGroup === "income" ? incomeItems : spendingItems) ?? []}
                onClose={() => setSelectedGroup(null)}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function isFlowGroup(id: string): id is FlowGroup {
  return id === "income" || id === "spending";
}

function FlowSvg({
  income,
  spending,
  totalIncome,
  totalSpending,
  selectedGroup,
  onSelectGroup,
}: {
  income: CategorySlice[];
  spending: CategorySlice[];
  totalIncome: number;
  totalSpending: number;
  selectedGroup: FlowGroup | null;
  onSelectGroup: (group: FlowGroup) => void;
}) {
  const { nodes, links } = layoutFlow(income, spending, totalIncome, totalSpending);
  const root = nodes.find((n) => n.id === "networth");

  function groupInteractionProps(id: string) {
    if (!isFlowGroup(id)) return {};
    return {
      onClick: () => onSelectGroup(id),
      onKeyDown: (e: ReactKeyboardEvent) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelectGroup(id);
        }
      },
      role: "button",
      tabIndex: 0,
      className: "cursor-pointer outline-none",
      "aria-label": `${selectedGroup === id ? "Hide" : "Show"} ${id} transactions`,
      "aria-pressed": selectedGroup === id,
    };
  }

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="mt-3 w-full max-w-xl mx-auto block" role="img" aria-label="Net worth flow diagram">
      {links.map((link) => {
        const source = link.source as LayoutNode;
        const target = link.target as LayoutNode;
        const width = link.width ?? 0;
        const y0 = link.y0 ?? 0;
        const y1 = link.y1 ?? 0;
        return (
          <g key={`${source.id}->${target.id}`} {...groupInteractionProps(target.id)}>
            <path
              d={ribbonPath(source.x1 ?? 0, y0 - width / 2, y0 + width / 2, target.x0 ?? 0, y1 - width / 2, y1 + width / 2)}
              fill={link.color}
              opacity={target.id === "income" || target.id === "spending" ? 0.25 : 0.35}
            >
              <title>
                {target.name}: {formatMoney(link.value)}
                {isFlowGroup(target.id) ? " (click to search transactions)" : ""}
              </title>
            </path>
            {width >= 10 && (
              <text x={(target.x0 ?? 0) - LABEL_GAP} y={y1 + 3.5} textAnchor="end" className="fill-ink text-[11px]">
                {target.name}: {formatMoney(link.value)}
              </text>
            )}
          </g>
        );
      })}

      {/* Root node has no incoming ribbon to carry its label, so it gets one to its left */}
      {root && (
        <text
          x={(root.x0 ?? 0) - LABEL_GAP}
          y={((root.y0 ?? 0) + (root.y1 ?? 0)) / 2 + 3.5}
          textAnchor="end"
          className="fill-ink text-[11px] font-medium"
        >
          {root.name}: {formatMoney(root.amount)}
        </text>
      )}

      {nodes.map((node) => {
        const x0 = node.x0 ?? 0;
        const x1 = node.x1 ?? 0;
        const y0 = node.y0 ?? 0;
        const y1 = node.y1 ?? 0;
        const isSelected = selectedGroup === node.id;
        return (
          <rect
            key={node.id}
            x={x0}
            y={y0}
            width={x1 - x0}
            height={Math.max(y1 - y0, 2)}
            rx={2}
            fill={node.color}
            stroke={isSelected ? "#ffffff" : "none"}
            strokeWidth={isSelected ? 1.5 : 0}
            {...groupInteractionProps(node.id)}
          >
            {isFlowGroup(node.id) && <title>Click to search {node.name.toLowerCase()} transactions</title>}
          </rect>
        );
      })}
    </svg>
  );
}

function FlowLegend({
  income,
  spending,
  totalIncome,
  totalSpending,
}: {
  income: CategorySlice[];
  spending: CategorySlice[];
  totalIncome: number;
  totalSpending: number;
}) {
  return (
    <div className="mt-4 grid grid-cols-1 gap-4 border-t border-border pt-3 sm:grid-cols-2">
      <div>
        <div className="text-[11px] font-medium text-ink-faint">Income · {formatMoney(totalIncome)}</div>
        <ul className="mt-1.5 space-y-1">
          {income.length === 0 && <li className="text-xs text-ink-faint">Nothing this month.</li>}
          {income.map((c) => (
            <li key={c.name} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2 text-ink">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: colorForCategory(c.name) }} />
                {c.name}
              </span>
              <span className="font-tabular text-ink-soft">{formatMoney(c.amount)}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <div className="text-[11px] font-medium text-ink-faint">Spending · {formatMoney(totalSpending)}</div>
        <ul className="mt-1.5 space-y-1">
          {spending.length === 0 && <li className="text-xs text-ink-faint">Nothing this month.</li>}
          {spending.map((c) => (
            <li key={c.name} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2 text-ink">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: colorForCategory(c.name) }} />
                {c.name}
              </span>
              <span className="font-tabular text-ink-soft">{formatMoney(c.amount)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ItemSearchPanel({
  group,
  items,
  onClose,
}: {
  group: FlowGroup;
  items: ItemizedItem[];
  onClose: () => void;
}) {
  return (
    <div className="mt-4 rounded-xl border border-border bg-bg p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-ink">{group === "income" ? "Income" : "Spending"} transactions</h3>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close transaction search"
          className="rounded-full p-1 text-ink-soft transition-colors hover:bg-surface hover:text-ink cursor-pointer"
        >
          <CloseIcon />
        </button>
      </div>
      <div className="mt-3">
        <TransactionSearch items={items} group={group} />
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

/** The accounts net worth is made of, so the headline figure visibly adds
 * up -- assets minus what's owed on cards and loans. */
function AccountBreakdown({ breakdown }: { breakdown: NetWorthHistory | null }) {
  if (breakdown === null) {
    return <div className="mt-4 h-24 animate-pulse rounded-xl bg-bg" />;
  }
  if (breakdown.accounts.length === 0) {
    return <p className="mt-4 text-sm text-ink-faint">No account balances synced yet.</p>;
  }
  const accountName = (a: NetWorthHistory["accounts"][number]) =>
    `${a.institution} ${a.name ?? a.type}${a.mask ? ` ••${a.mask}` : ""}`;

  return (
    <div className="mt-4 rounded-xl border border-border">
      <ul className="divide-y divide-border text-sm">
        {breakdown.accounts.map((a, i) => (
          <li key={i} className="flex items-center justify-between px-4 py-2.5">
            <div className="min-w-0">
              <div className="truncate text-ink">{accountName(a)}</div>
              <div className="text-xs capitalize text-ink-faint">
                {a.type} · {a.kind === "liability" ? "owed" : "asset"}
              </div>
            </div>
            <span className={`font-tabular shrink-0 pl-3 ${a.kind === "liability" ? "text-danger" : "text-ink"}`}>
              {a.kind === "liability" ? "−" : ""}
              {formatMoney(a.balance)}
            </span>
          </li>
        ))}
        {breakdown.excluded_accounts.map((a, i) => (
          <li key={`x${i}`} className="flex items-center justify-between px-4 py-2.5 opacity-60">
            <div className="min-w-0">
              <div className="truncate text-ink">{accountName(a)}</div>
              <div className="text-xs text-ink-faint">Not included · {a.reason}</div>
            </div>
            <span className="font-tabular shrink-0 pl-3 text-ink-faint">{formatMoney(a.balance)}</span>
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between border-t border-border bg-bg px-4 py-2.5 text-sm font-semibold">
        <span className="text-ink">Net worth</span>
        <span className="font-tabular text-ink">{breakdown.current !== null ? formatMoney(breakdown.current) : "—"}</span>
      </div>
    </div>
  );
}
