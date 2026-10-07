import { useEffect, useRef, useState, type ReactNode } from "react";
import { fetchCashFlow, type CashFlowBreakdown } from "../lib/api";
import { PERIODS, periodInfo, type Period } from "../lib/period";
import { SpendingPaceChart } from "../components/SpendingPaceChart";

const whole = (n: number) => "$" + Math.round(n).toLocaleString("en-US");
const MAX_CATEGORIES = 8;

type Kind = "income" | "deficit" | "spend" | "kept";

interface FlowNode {
  name: string;
  amount: number;
  kind: Kind;
  /** Where clicking it goes in Transactions, if anywhere. */
  target?: { category: string | null; query: string };
}

const KIND_COLOR: Record<Kind, string> = {
  income: "var(--color-signal)",
  deficit: "var(--color-warn)",
  spend: "var(--color-spend)",
  kept: "var(--color-positive)",
};

/** Income sources on the left; spending categories plus what's left on the right. Both sides sum to the same total. */
function sides(flow: CashFlowBreakdown): { left: FlowNode[]; right: FlowNode[]; total: number } {
  const left: FlowNode[] = flow.sources.map((s) => ({
    name: s.name,
    amount: s.amount,
    kind: "income",
    // "N other sources" is a roll-up, so it lists every income row.
    target: { category: "Income", query: /^\d+ other sources$/.test(s.name) ? "" : s.name },
  }));
  if (flow.spending > flow.income) {
    left.push({ name: "From your balances", amount: flow.spending - flow.income, kind: "deficit" });
  }

  const cats = flow.categories;
  const shown = cats.length > MAX_CATEGORIES ? cats.slice(0, MAX_CATEGORIES - 1) : cats;
  const right: FlowNode[] = shown.map((c) => ({ name: c.name, amount: c.amount, kind: "spend", target: { category: c.name, query: "" } }));
  if (cats.length > shown.length) {
    // A roll-up of several categories has no single filter to open.
    const tail = cats.slice(shown.length);
    right.push({ name: `${tail.length} more`, amount: tail.reduce((s, c) => s + c.amount, 0), kind: "spend" });
  }
  if (flow.net > 0) right.push({ name: "Left over", amount: flow.net, kind: "kept" });

  return { left, right, total: Math.max(flow.income, flow.spending) };
}

export function CashFlowView({
  token,
  period,
  onPeriodChange,
  onOpenTransactions,
  refreshKey,
}: {
  token: string;
  period: Period;
  onPeriodChange: (period: Period) => void;
  onOpenTransactions: (filter: { category: string | null; query: string }) => void;
  refreshKey?: unknown;
}) {
  const [flow, setFlow] = useState<CashFlowBreakdown | null>(null);
  const [failed, setFailed] = useState(false);
  const window_ = periodInfo(period).window;

  useEffect(() => {
    let stale = false;
    setFlow(null);
    setFailed(false);
    fetchCashFlow(token, window_)
      .then((f) => !stale && setFlow(f))
      .catch(() => !stale && setFailed(true));
    return () => {
      stale = true;
    };
  }, [token, window_, refreshKey]);

  const data = flow ? sides(flow) : null;
  const empty = flow !== null && flow.income === 0 && flow.spending === 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto animate-view">
      <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-4 px-4 py-4 lg:px-8 lg:py-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h1 className="m-0 text-[22px] font-semibold tracking-[-0.02em] text-ink lg:text-[26px]">Cash flow</h1>
            <span className="text-[13px] text-ink-soft">
              Where your money came from and where it went{flow ? ` · ${flow.label}` : ""}. Pick a category to see its transactions.
            </span>
          </div>
          <div role="radiogroup" aria-label="Period" className="-mx-4 flex overflow-x-auto px-4 lg:mx-0 lg:px-0">
            <div className="flex rounded-[14px] bg-surface p-[3px]">
              {PERIODS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  role="radio"
                  aria-checked={p.value === period}
                  onClick={() => onPeriodChange(p.value)}
                  className={`h-[38px] shrink-0 cursor-pointer whitespace-nowrap rounded-[11px] px-3.5 text-[13px] ${
                    p.value === period ? "bg-raised text-ink" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {failed ? (
          <Panel>
            <p className="py-10 text-center text-sm text-ink-soft">Couldn’t load cash flow. Switch views to try again.</p>
          </Panel>
        ) : !flow || !data ? (
          <div className="h-[420px] animate-pulse rounded-3xl bg-surface" aria-label="Loading cash flow" />
        ) : empty ? (
          <Panel>
            <p className="py-10 text-center text-sm text-ink-soft">No income or spending in {flow.label} yet.</p>
          </Panel>
        ) : (
          <>
            <Panel className="hidden md:block">
              <Sankey flow={flow} {...data} onPick={onOpenTransactions} />
            </Panel>
            <CompactFlow flow={flow} {...data} onPick={onOpenTransactions} />
          </>
        )}

        <SpendingPaceChart token={token} refreshKey={refreshKey} />
      </div>
    </div>
  );
}

function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-3xl bg-surface p-4 md:px-7 md:py-6 ${className}`}>{children}</div>;
}

const W = 980;
const H = 520;
const NODE_W = 12;
const XL = 200;
const XM = 470;
const XR = 700;
const GAP_L = 28;
const GAP_R = 18;

/**
 * Labels are HTML at a fixed pixel size over a scaling SVG, so small nodes'
 * labels collide. Push each one down to keep `gap` (in SVG units) from the
 * one above, then pull the stack back up if it ran off the bottom.
 */
function spread(ys: number[], gap: number, min: number, max: number): number[] {
  const out = [...ys];
  for (let i = 1; i < out.length; i++) out[i] = Math.max(out[i], out[i - 1] + gap);
  const overflow = out.length ? out[out.length - 1] - max : 0;
  if (overflow > 0) {
    out[out.length - 1] -= overflow;
    for (let i = out.length - 2; i >= 0; i--) out[i] = Math.min(out[i], out[i + 1] - gap);
  }
  return out.map((y) => Math.max(y, min));
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(W);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width || W));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

function ribbon(x0: number, a0: number, b0: number, x1: number, a1: number, b1: number) {
  const m = (x0 + x1) / 2;
  return `M${x0},${a0} C${m},${a0} ${m},${a1} ${x1},${a1} L${x1},${b1} C${m},${b1} ${m},${b0} ${x0},${b0} Z`;
}

function Sankey({
  flow,
  left,
  right,
  total,
  onPick,
}: {
  flow: CashFlowBreakdown;
  left: FlowNode[];
  right: FlowNode[];
  total: number;
  onPick: (filter: { category: string | null; query: string }) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const [boxRef, width] = useWidth<HTMLDivElement>();
  const scale = width / W;
  const k = (H - GAP_R * Math.max(right.length - 1, 0)) / total;
  const midH = total * k;
  const midY = (H - midH) / 2;

  const rects: { x: number; y: number; h: number; color: string }[] = [];
  const links: { d: string; color: string; name: string }[] = [];
  const labels: { node: FlowNode; side: "left" | "right"; y: number }[] = [];

  const leftH = total * k + GAP_L * Math.max(left.length - 1, 0);
  let y = (H - leftH) / 2;
  let mIn = midY;
  for (const node of left) {
    const h = node.amount * k;
    rects.push({ x: XL, y, h: Math.max(h, 2), color: KIND_COLOR[node.kind] });
    links.push({ d: ribbon(XL + NODE_W, y, y + h, XM, mIn, mIn + h), color: KIND_COLOR[node.kind], name: node.name });
    labels.push({ node, side: "left", y: y + h / 2 });
    y += h + GAP_L;
    mIn += h;
  }
  rects.push({ x: XM, y: midY, h: midH, color: "var(--color-ink)" });

  let yr = 0;
  let mOut = midY;
  for (const node of right) {
    const h = node.amount * k;
    rects.push({ x: XR, y: yr, h: Math.max(h, 2), color: KIND_COLOR[node.kind] });
    links.push({ d: ribbon(XM + NODE_W, mOut, mOut + h, XR, yr, yr + h), color: KIND_COLOR[node.kind], name: node.name });
    labels.push({ node, side: "right", y: yr + h / 2 });
    yr += h + GAP_R;
    mOut += h;
  }

  const leftYs = spread(labels.filter((l) => l.side === "left").map((l) => l.y), 38 / scale, -10, H + 10);
  const rightYs = spread(labels.filter((l) => l.side === "right").map((l) => l.y), 22 / scale, -10, H + 10);
  let li = 0;
  let ri = 0;
  for (const l of labels) l.y = l.side === "left" ? leftYs[li++] : rightYs[ri++];

  const pct = (n: number) => `${Math.round((n / total) * 100)}%`;
  const aria = `Cash flow for ${flow.label}: ${whole(flow.income)} income from ${flow.sources.length} source${flow.sources.length === 1 ? "" : "s"}, ${whole(flow.spending)} spending across ${flow.categories.length} categories${flow.net > 0 ? `, ${whole(flow.net)} left over` : `, ${whole(-flow.net)} more out than in`}.`;

  return (
    <div ref={boxRef} className="relative mx-auto w-full max-w-[980px]" style={{ aspectRatio: `${W} / ${H + 40}` }}>
      <svg role="img" aria-label={aria} viewBox={`0 -20 ${W} ${H + 40}`} className="absolute inset-0 h-full w-full overflow-visible">
        {links.map((l) => (
          <path
            key={l.name}
            d={l.d}
            fill={l.color}
            opacity={hover ? (hover === l.name ? 0.55 : 0.08) : 0.28}
            className="transition-opacity duration-150"
          />
        ))}
        {rects.map((r, i) => (
          <rect key={i} x={r.x} y={r.y} width={NODE_W} height={r.h} rx="3" fill={r.color} />
        ))}
      </svg>

      <div
        className="pointer-events-none absolute flex -translate-x-1/2 -translate-y-1/2 items-center gap-2 whitespace-nowrap"
        style={{ left: `${((XM + NODE_W / 2) / W) * 100}%`, top: `${((midY - 12 + 20) / (H + 40)) * 100}%` }}
      >
        <span className="text-[13px] font-medium text-ink">{flow.spending > flow.income ? "Money out" : "Income"}</span>
        <span className="font-tabular text-[11px] text-ink-soft">{whole(total)}</span>
      </div>

      {labels.map(({ node, side, y: ly }) => {
        const top = `${((ly + 20) / (H + 40)) * 100}%`;
        const style =
          side === "left"
            ? { right: `${((W - XL + 6) / W) * 100}%`, top, maxWidth: `${((XL - 6) / W) * 100}%` }
            : { left: `${((XR + NODE_W + 4) / W) * 100}%`, top };
        const color = KIND_COLOR[node.kind];
        const content = (
          <>
            <span className={`text-[13px] font-medium text-ink ${side === "left" ? "max-w-full truncate" : ""}`} title={node.name}>
              {node.name}
            </span>
            <span className="font-tabular text-[11px]" style={{ color }}>
              {whole(node.amount)} · {pct(node.amount)}
            </span>
          </>
        );
        // Left labels stack name over amount so long payer names fit their column.
        const base = `absolute flex -translate-y-1/2 whitespace-nowrap rounded-md px-1.5 ${
          side === "left" ? "flex-col items-end py-0.5" : "h-6 items-center gap-2"
        }`;
        return node.target ? (
          <button
            key={node.name}
            type="button"
            onClick={() => onPick(node.target!)}
            onMouseEnter={() => setHover(node.name)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(node.name)}
            onBlur={() => setHover(null)}
            aria-label={`${node.name}: ${whole(node.amount)}. Show transactions`}
            className={`${base} cursor-pointer hover:bg-raised`}
            style={style}
          >
            {content}
          </button>
        ) : (
          <span key={node.name} className={base} style={style} onMouseEnter={() => setHover(node.name)} onMouseLeave={() => setHover(null)}>
            {content}
          </span>
        );
      })}
    </div>
  );
}

/** Phones: income bar, the split, spent vs kept, then every category as a tappable row. */
function CompactFlow({
  flow,
  left,
  right,
  total,
  onPick,
}: {
  flow: CashFlowBreakdown;
  left: FlowNode[];
  right: FlowNode[];
  total: number;
  onPick: (filter: { category: string | null; query: string }) => void;
}) {
  const spentPct = (flow.spending / total) * 100;
  const maxRow = Math.max(...right.map((r) => r.amount), 1);
  return (
    <div className="flex flex-col gap-3 md:hidden">
      <div className="flex flex-col gap-2.5 rounded-[18px] bg-surface p-3.5">
        <div className="flex justify-between text-[13px]">
          <span className="text-ink">↓ Income</span>
          <span className="font-tabular text-signal">{whole(flow.income)}</span>
        </div>
        <div className="flex h-3.5 gap-0.5 overflow-hidden rounded">
          {left.map((s, i) => (
            <div
              key={s.name}
              style={{ width: `${(s.amount / total) * 100}%`, background: KIND_COLOR[s.kind], opacity: s.kind === "income" ? 1 - i * 0.25 : 1 }}
            />
          ))}
        </div>
        <span className="font-tabular text-[11px] text-ink-soft">{left.map((s) => `${s.name} ${whole(s.amount)}`).join(" · ")}</span>
        <div className="flex h-3.5 gap-0.5 overflow-hidden rounded">
          <div className="bg-spend" style={{ width: `${spentPct}%` }} />
          {flow.net > 0 && <div className="bg-positive" style={{ width: `${100 - spentPct}%` }} />}
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-spend">Spent {whole(flow.spending)}</span>
          {flow.net > 0 ? <span className="text-positive">Kept {whole(flow.net)}</span> : <span className="text-warn">{whole(-flow.net)} more out than in</span>}
        </div>
      </div>
      <ul className="rounded-[18px] bg-surface px-3.5 py-1">
        {right.map((c, i) => {
          const body = (
            <>
              <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: KIND_COLOR[c.kind] }} />
              <span className="flex-1 truncate text-left text-sm text-ink">{c.name}</span>
              <span className="h-1 w-[70px] shrink-0 rounded-full bg-line">
                <span className="block h-1 rounded-full" style={{ width: `${(c.amount / maxRow) * 100}%`, background: KIND_COLOR[c.kind] }} />
              </span>
              <span className="w-16 text-right font-tabular text-[13px] text-ink">{whole(c.amount)}</span>
              <span aria-hidden className="w-2 text-ink-faint">{c.target ? "›" : ""}</span>
            </>
          );
          const cls = `flex min-h-11 w-full items-center gap-2.5 ${i ? "border-t border-line" : ""}`;
          return (
            <li key={c.name}>
              {c.target ? (
                <button type="button" onClick={() => onPick(c.target!)} className={`${cls} cursor-pointer`}>
                  {body}
                </button>
              ) : (
                <div className={cls}>{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
