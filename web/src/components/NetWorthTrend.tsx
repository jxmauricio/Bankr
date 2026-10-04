import { formatMoney } from "../lib/format";

type Point = { date: string; net_worth: number };

const DAY_MS = 86_400_000;

/** The change across the (already windowed) history. Null until there are at
 * least `minDays` between its first and last snapshot. */
export function netWorthChange(
  history: Point[],
  minDays = 7,
): { delta: number; pct: number | null; since: string } | null {
  if (history.length < 2) return null;
  const first = history[0];
  const last = history[history.length - 1];
  if (new Date(last.date).getTime() - new Date(first.date).getTime() < minDays * DAY_MS) return null;
  const delta = last.net_worth - first.net_worth;
  const pct = first.net_worth !== 0 ? (delta / Math.abs(first.net_worth)) * 100 : null;
  return {
    delta,
    pct,
    since: new Date(first.date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }),
  };
}

export function ChangePill({ history, minDays = 7 }: { history: Point[]; minDays?: number }) {
  const change = netWorthChange(history, minDays);
  if (!change) {
    return (
      <span className="text-[13px] text-ink-soft">
        {history.length === 0
          ? "No net worth history for this period."
          : "Trend and change appear after your first full week of history."}
      </span>
    );
  }
  const up = change.delta >= 0;
  const money = formatMoney(Math.abs(change.delta));
  return (
    <span className="flex items-center gap-2">
      <span
        className={`rounded-full px-2.5 py-1 font-mono text-xs font-medium tabular-nums ${
          up ? "bg-positive-soft text-positive" : "bg-negative-soft text-negative"
        }`}
      >
        {up ? "▲ +" : "▼ −"}
        {money}
        {change.pct !== null && ` · ${Math.abs(change.pct).toFixed(1)}%`}
      </span>
      <span className="text-xs text-ink-faint">since {change.since}</span>
    </span>
  );
}

/** Net worth line over the given window, with a dashed baseline at its starting value. */
export function Sparkline({ history }: { history: Point[] }) {
  const recent = history;
  if (recent.length < 2) return null;
  const values = recent.map((p) => p.net_worth);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const W = 600;
  const H = 60;
  const pts = recent.map((p, i) => {
    const x = (i / (recent.length - 1)) * W;
    const y = H - 6 - ((p.net_worth - min) / span) * (H - 14);
    return [x, y] as const;
  });
  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const rising = values[values.length - 1] >= values[0];
  return (
    <svg
      role="img"
      aria-label={`Net worth over the last ${recent.length} days, ${rising ? "rising" : "falling"}`}
      width="100%"
      height="60"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="mt-3.5 block"
    >
      <path d={`${line} L${W} ${H} L0 ${H}Z`} fill="var(--color-signal)" fillOpacity="0.1" />
      <line
        x1="0"
        y1={pts[0][1]}
        x2={W}
        y2={pts[0][1]}
        stroke="var(--color-line-strong)"
        strokeDasharray="3 4"
        vectorEffect="non-scaling-stroke"
      />
      <path d={line} fill="none" stroke="var(--color-signal)" strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
