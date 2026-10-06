import type { ChartPoint, ChartSpec } from "../lib/api";
import { colorForCategory, hasCategoryColor } from "../lib/chartColors";
import { formatMoney } from "../lib/format";

/** A small chart under a chat reply. The numbers are built server-side from a
 * fresh query (tools.show_chart), never written by the model, so they always
 * match the dashboard. Three deliberately plain shapes: bars for "where did it
 * go", two bars for "then vs now", and month columns for "how has it moved". */
export function ChatChart({ chart }: { chart: ChartSpec }) {
  if (chart.points.length === 0) return null;
  return (
    <figure className="m-0 flex w-full max-w-[520px] flex-col gap-3 rounded-2xl bg-raised p-4">
      <figcaption className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-ink">{chart.title}</span>
        {chart.period && <span className="shrink-0 text-xs text-ink-faint">{chart.period}</span>}
      </figcaption>
      {chart.kind === "breakdown" && <Breakdown points={chart.points} />}
      {chart.kind === "compare" && <Compare chart={chart} />}
      {chart.kind === "trend" && <Trend points={chart.points} />}
    </figure>
  );
}

function barColor(label: string): string {
  if (/^\d+ others$/.test(label)) return "var(--color-ink-faint)";
  return hasCategoryColor(label) ? colorForCategory(label) : "var(--color-signal)";
}

function Bar({ fraction, color }: { fraction: number; color: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-line">
      <div
        className="chart-grow h-full rounded-full"
        style={{ width: `${Math.max(fraction * 100, 2)}%`, backgroundColor: color }}
      />
    </div>
  );
}

function Breakdown({ points }: { points: ChartPoint[] }) {
  const max = Math.max(...points.map((p) => p.value));
  return (
    <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
      {points.map((p) => (
        <li key={p.label} className="flex flex-col gap-1">
          <div className="flex items-baseline justify-between gap-3 text-[13px]">
            <span className="truncate text-ink-soft">{p.label}</span>
            <span className="shrink-0 font-mono tabular-nums text-ink">
              {formatMoney(p.value)}
              {p.share != null && <span className="ml-2 text-ink-faint">{Math.round(p.share * 100)}%</span>}
            </span>
          </div>
          <Bar fraction={max ? p.value / max : 0} color={barColor(p.label)} />
        </li>
      ))}
    </ul>
  );
}

function Compare({ chart }: { chart: ChartSpec }) {
  const [previous, current] = chart.points;
  const max = Math.max(previous.value, current.value);
  const change = chart.change;
  // Spending more is the bad direction, so "up" reads in the negative color.
  const tone =
    change?.direction === "up"
      ? "bg-negative-soft text-negative"
      : change?.direction === "down"
        ? "bg-positive-soft text-positive"
        : "bg-line text-ink-soft";
  return (
    <div className="flex flex-col gap-2.5">
      {[
        { point: previous, color: "var(--color-line-strong)" },
        { point: current, color: "var(--color-signal)" },
      ].map(({ point, color }) => (
        <div key={point.label} className="flex flex-col gap-1">
          <div className="flex items-baseline justify-between gap-3 text-[13px]">
            <span className="text-ink-soft">{point.label}</span>
            <span className="font-mono tabular-nums text-ink">{formatMoney(point.value)}</span>
          </div>
          <Bar fraction={max ? point.value / max : 0} color={color} />
        </div>
      ))}
      {change && (
        <span className={`self-start rounded-full px-2.5 py-1 font-mono text-xs font-medium tabular-nums ${tone}`}>
          {change.direction === "up" ? "▲ +" : change.direction === "down" ? "▼ −" : ""}
          {formatMoney(Math.abs(change.difference))}
          {change.percent_change !== null && ` · ${Math.abs(change.percent_change).toFixed(0)}%`}
        </span>
      )}
    </div>
  );
}

function Trend({ points }: { points: ChartPoint[] }) {
  const max = Math.max(...points.map((p) => Math.abs(p.value))) || 1;
  const last = points[points.length - 1];
  return (
    <div
      role="img"
      aria-label={points.map((p) => `${p.label} ${formatMoney(p.value)}${p.partial ? " so far" : ""}`).join(", ")}
      className="flex flex-col gap-1.5"
    >
      <div className="flex h-24 items-end gap-2">
        {points.map((p, i) => {
          const isLast = i === points.length - 1;
          const color =
            p.value < 0 ? "var(--color-negative)" : isLast ? "var(--color-signal)" : "var(--color-line-strong)";
          return (
            <div key={p.label + i} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
              {isLast && (
                <span className="font-mono text-[11px] tabular-nums text-ink">{formatMoney(last.value)}</span>
              )}
              <div
                title={`${p.label}: ${formatMoney(p.value)}${p.partial ? " so far" : ""}`}
                className={`chart-rise w-full max-w-10 rounded-t-md ${p.partial ? "opacity-70" : ""}`}
                style={{ height: `${Math.max((Math.abs(p.value) / max) * 100, 3)}%`, backgroundColor: color }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex gap-2">
        {points.map((p, i) => (
          <span key={p.label + i} className="flex-1 text-center text-[11px] text-ink-faint">
            {p.label}
            {p.partial && "*"}
          </span>
        ))}
      </div>
      {last.partial && <span className="text-[11px] text-ink-faint">* month so far</span>}
    </div>
  );
}
