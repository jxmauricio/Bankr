import { useEffect, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { sankey, type SankeyNode } from "d3-sankey";
import { fetchIncome, fetchNetWorth, fetchSpending, type ItemizedItem, type NetWorthHistory } from "../lib/api";
import { formatMoney } from "../lib/format";
import { TransactionSearch } from "./TransactionSearch";

type FlowGroup = "income" | "spending";
type ChartView = "flow" | "pie" | "bars";

const CHART_VIEWS: { id: ChartView; label: string }[] = [
  { id: "flow", label: "Flow" },
  { id: "pie", label: "Pie" },
  { id: "bars", label: "Bars" },
];
const PIE_SLICE_CAP = 7;

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
  "Restaurants",
  "Fast Food",
  "Coffee",
  "Alcohol & Bars",
  "Gas",
  "Rideshare & Taxi",
  "Public Transit",
  "Parking & Tolls",
  "Auto Maintenance",
  "Travel",
  "Loan Payments",
  "Fees",
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
  members?: string[];
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

/** Pie charts get noisy past ~7 slices; fold the tail into Other. */
function pieSlicesForChart(slices: CategorySlice[]): CategorySlice[] {
  if (slices.length <= PIE_SLICE_CAP) return slices;
  const head = slices.slice(0, PIE_SLICE_CAP - 1);
  const tail = slices.slice(PIE_SLICE_CAP - 1);
  return [
    ...head,
    {
      name: "Other",
      amount: tail.reduce((sum, slice) => sum + slice.amount, 0),
      members: tail.map((slice) => slice.name),
    },
  ];
}

function itemsForSlice(items: ItemizedItem[], slice: CategorySlice | null): ItemizedItem[] {
  if (!slice) return items;
  const names = new Set(slice.members ?? [slice.name]);
  return items.filter((item) => names.has(item.category ?? "Uncategorized"));
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
  const [selectedSlice, setSelectedSlice] = useState<CategorySlice | null>(null);
  const [chartView, setChartView] = useState<ChartView>("flow");
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
    setSelectedSlice(null);
    setSelectedGroup((prev) => (prev === group ? null : group));
  }

  function toggleSlice(slice: CategorySlice) {
    setSelectedGroup(null);
    setSelectedSlice((prev) => (prev?.name === slice.name ? null : slice));
  }

  function changeView(view: ChartView) {
    setChartView(view);
    setSelectedGroup(null);
    setSelectedSlice(null);
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

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="font-display text-lg font-semibold text-ink">
              {chartView === "flow" ? "This month's flow" : "This month's spending"}
            </h2>
            <p className="mt-1 text-sm text-ink-faint">
              {chartView === "flow"
                ? `Net worth ${netWorth !== null ? formatMoney(netWorth) : "—"} · illustrative, not a literal period-over-period reconciliation`
                : chartView === "pie"
                  ? "Share of spending by category. Click a slice to see the charges."
                  : "Biggest categories first. Click a bar to see the charges."}
            </p>
          </div>
          <ChartViewToggle value={chartView} onChange={changeView} />
        </div>

        {loading ? (
          <div className="mt-8 flex h-64 items-center justify-center text-sm text-ink-faint">Loading…</div>
        ) : chartView === "flow" ? (
          grandTotal === 0 ? (
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
          )
        ) : totalSpending === 0 ? (
          <div className="mt-8 flex h-64 items-center justify-center text-sm text-ink-faint">
            No spending recorded this month yet.
          </div>
        ) : (
          <>
            {chartView === "pie" ? (
              <SpendingPie slices={spending!} total={totalSpending} selected={selectedSlice} onSelect={toggleSlice} />
            ) : (
              <SpendingBars slices={spending!} total={totalSpending} selected={selectedSlice} onSelect={toggleSlice} />
            )}
            {selectedSlice && (
              <ItemSearchPanel
                key={selectedSlice.name}
                group="spending"
                category={selectedSlice.name}
                items={itemsForSlice(spendingItems ?? [], selectedSlice)}
                onClose={() => setSelectedSlice(null)}
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

function ChartViewToggle({ value, onChange }: { value: ChartView; onChange: (view: ChartView) => void }) {
  return (
    <div className="inline-flex shrink-0 rounded-full border border-border bg-bg p-0.5 text-xs" role="tablist" aria-label="Spending chart">
      {CHART_VIEWS.map((view) => (
        <button
          key={view.id}
          type="button"
          role="tab"
          aria-selected={value === view.id}
          onClick={() => onChange(view.id)}
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1.5 transition-colors cursor-pointer ${
            value === view.id ? "bg-accent text-white" : "text-ink-soft hover:text-ink"
          }`}
        >
          <ChartViewIcon view={view.id} />
          {view.label}
        </button>
      ))}
    </div>
  );
}

function ChartViewIcon({ view }: { view: ChartView }) {
  if (view === "pie") {
    return (
      <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
        <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5H8V1.5Z" opacity="0.55" />
        <path d="M8 1.5A6.5 6.5 0 0 1 14.5 8H8V1.5Z" />
      </svg>
    );
  }
  if (view === "bars") {
    return (
      <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
        <rect x="1.5" y="10" width="13" height="2.2" rx="0.6" />
        <rect x="1.5" y="6.4" width="9.5" height="2.2" rx="0.6" opacity="0.75" />
        <rect x="1.5" y="2.8" width="6" height="2.2" rx="0.6" opacity="0.5" />
      </svg>
    );
  }
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden>
      <path d="M2 3.5h2.2v9H2zM6.9 6h2.2v6.5H6.9zM11.8 4.5H14v8h-2.2z" fill="currentColor" stroke="none" />
    </svg>
  );
}

const PIE_SIZE = 280;
const PIE_CX = PIE_SIZE / 2;
const PIE_CY = PIE_SIZE / 2;
const PIE_OUTER = 108;
const PIE_INNER = 64;

function polar(cx: number, cy: number, r: number, angle: number): [number, number] {
  return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
}

function donutPath(cx: number, cy: number, inner: number, outer: number, start: number, end: number): string {
  const span = end - start;
  if (span >= Math.PI * 2 - 1e-6) {
    return [
      `M ${cx + outer} ${cy}`,
      `A ${outer} ${outer} 0 1 1 ${cx - outer} ${cy}`,
      `A ${outer} ${outer} 0 1 1 ${cx + outer} ${cy}`,
      `M ${cx + inner} ${cy}`,
      `A ${inner} ${inner} 0 1 0 ${cx - inner} ${cy}`,
      `A ${inner} ${inner} 0 1 0 ${cx + inner} ${cy}`,
    ].join(" ");
  }
  const large = span > Math.PI ? 1 : 0;
  const [x0, y0] = polar(cx, cy, outer, start);
  const [x1, y1] = polar(cx, cy, outer, end);
  const [x2, y2] = polar(cx, cy, inner, end);
  const [x3, y3] = polar(cx, cy, inner, start);
  return `M${x0},${y0} A${outer},${outer} 0 ${large} 1 ${x1},${y1} L${x2},${y2} A${inner},${inner} 0 ${large} 0 ${x3},${y3} Z`;
}

function SpendingPie({
  slices,
  total,
  selected,
  onSelect,
}: {
  slices: CategorySlice[];
  total: number;
  selected: CategorySlice | null;
  onSelect: (slice: CategorySlice) => void;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const chartSlices = pieSlicesForChart(slices);
  let angle = -Math.PI / 2;
  const arcs = chartSlices.map((slice) => {
    const start = angle;
    angle += (slice.amount / total) * Math.PI * 2;
    return { slice, start, end: angle };
  });
  const focus = chartSlices.find((s) => s.name === (hovered ?? selected?.name)) ?? null;
  const holeLabel = focus?.name ?? "Spending";
  const holeAmount = focus?.amount ?? total;
  const holeShare = ((holeAmount / total) * 100).toFixed(0);

  return (
    <div className="mt-4 flex flex-col items-center gap-6 lg:flex-row lg:items-start lg:justify-center">
      <svg viewBox={`0 0 ${PIE_SIZE} ${PIE_SIZE}`} className="h-64 w-64 shrink-0" role="img" aria-label="Spending by category">
        {arcs.map(({ slice, start, end }) => {
          const isFocus = !hovered && !selected ? true : slice.name === (hovered ?? selected?.name);
          return (
            <path
              key={slice.name}
              d={donutPath(PIE_CX, PIE_CY, PIE_INNER, PIE_OUTER, start, end)}
              fill={colorForCategory(slice.name)}
              opacity={isFocus ? 1 : 0.35}
              stroke={selected?.name === slice.name ? "#ffffff" : "var(--color-surface)"}
              strokeWidth={selected?.name === slice.name ? 2 : 1.5}
              className="cursor-pointer outline-none"
              role="button"
              tabIndex={0}
              aria-label={`${slice.name} ${formatMoney(slice.amount)}, ${((slice.amount / total) * 100).toFixed(0)} percent`}
              aria-pressed={selected?.name === slice.name}
              onClick={() => onSelect(slice)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(slice);
                }
              }}
              onMouseEnter={() => setHovered(slice.name)}
              onMouseLeave={() => setHovered(null)}
            >
              <title>
                {slice.name}: {formatMoney(slice.amount)} ({((slice.amount / total) * 100).toFixed(0)}%)
              </title>
            </path>
          );
        })}
        <text x={PIE_CX} y={PIE_CY - 10} textAnchor="middle" className="fill-ink-soft text-[11px]">
          {holeLabel}
        </text>
        <text x={PIE_CX} y={PIE_CY + 10} textAnchor="middle" className="fill-ink font-tabular text-sm font-semibold">
          {formatMoney(holeAmount)}
        </text>
        {focus && (
          <text x={PIE_CX} y={PIE_CY + 26} textAnchor="middle" className="fill-ink-faint font-tabular text-[10px]">
            {holeShare}%
          </text>
        )}
      </svg>
      <ul className="w-full max-w-xs space-y-1.5 pt-2">
        {chartSlices.map((slice) => (
          <li key={slice.name}>
            <button
              type="button"
              onClick={() => onSelect(slice)}
              onMouseEnter={() => setHovered(slice.name)}
              onMouseLeave={() => setHovered(null)}
              className={`flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-left text-xs transition-colors cursor-pointer ${
                selected?.name === slice.name ? "bg-accent-soft" : "hover:bg-bg"
              }`}
            >
              <span className="flex min-w-0 items-center gap-2 text-ink">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: colorForCategory(slice.name) }} />
                <span className="truncate">{slice.name}</span>
              </span>
              <span className="shrink-0 font-tabular text-ink-soft">
                {((slice.amount / total) * 100).toFixed(0)}% · {formatMoney(slice.amount)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SpendingBars({
  slices,
  total,
  selected,
  onSelect,
}: {
  slices: CategorySlice[];
  total: number;
  selected: CategorySlice | null;
  onSelect: (slice: CategorySlice) => void;
}) {
  const max = slices[0]?.amount ?? 1;
  return (
    <ul className="mt-5 space-y-2">
      {slices.map((slice) => {
        const isSelected = selected?.name === slice.name;
        return (
          <li key={slice.name}>
            <button
              type="button"
              onClick={() => onSelect(slice)}
              aria-pressed={isSelected}
              className={`w-full rounded-lg px-2 py-1.5 text-left transition-colors cursor-pointer ${
                isSelected ? "bg-accent-soft" : "hover:bg-bg"
              }`}
            >
              <div className="flex items-baseline justify-between gap-3 text-xs">
                <span className="truncate text-ink">{slice.name}</span>
                <span className="shrink-0 font-tabular text-ink-soft">
                  {formatMoney(slice.amount)} · {((slice.amount / total) * 100).toFixed(0)}%
                </span>
              </div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-bg">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.max((slice.amount / max) * 100, 2)}%`, backgroundColor: colorForCategory(slice.name) }}
                />
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
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
  category,
  onClose,
}: {
  group: FlowGroup;
  items: ItemizedItem[];
  category?: string;
  onClose: () => void;
}) {
  const title = category ?? (group === "income" ? "Income" : "Spending");
  return (
    <div className="mt-4 rounded-xl border border-border bg-bg p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-ink">{title} transactions</h3>
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
