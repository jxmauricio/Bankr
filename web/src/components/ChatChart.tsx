import { useEffect, useState, type ReactNode } from "react";
import { fetchQuery, type ChartPoint, type ChartSpec, type ItemizedTransactions, type SourceQuery } from "../lib/api";
import { colorForCategory, hasCategoryColor } from "../lib/chartColors";
import { formatDate, formatMoney } from "../lib/format";
import { RowAmount } from "./TransactionSearch";

/** A small chart under a chat reply. The numbers are built server-side from a
 * fresh query (tools.show_chart), never written by the model, so they always
 * match the dashboard. Three deliberately plain shapes: bars for "where did it
 * go", two bars for "then vs now", and month columns for "how has it moved".
 *
 * Every chart is described in full for screen readers, and comes with the
 * transactions it's drawn from: tap a bar to list only that bar's rows. A net
 * trend (income minus spending) is two lists at once, so it points to Cash
 * flow instead. */
export function ChatChart({
  chart,
  token,
  onOpenSource,
  onOpenCashFlow,
}: {
  chart: ChartSpec;
  token: string | null;
  onOpenSource: (query: SourceQuery) => void;
  onOpenCashFlow: () => void;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  if (chart.points.length === 0) return null;
  const pick = (i: number) => setSelected((s) => (s === i ? null : i));
  const selectedPoint = selected === null ? null : chart.points[selected];
  const query = selectedPoint?.query ?? chart.query ?? null;

  return (
    <figure className="m-0 flex w-full max-w-[520px] flex-col gap-3 rounded-2xl bg-raised p-4">
      <figcaption className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-ink">{chart.title}</span>
        {chart.period && <span className="shrink-0 text-xs text-ink-faint">{chart.period}</span>}
        <span className="sr-only">: {describeChart(chart)}</span>
      </figcaption>
      {chart.kind === "breakdown" && <Breakdown chart={chart} selected={selected} onPick={pick} />}
      {chart.kind === "compare" && <Compare chart={chart} selected={selected} onPick={pick} />}
      {chart.kind === "trend" && <Trend chart={chart} selected={selected} onPick={pick} />}
      {query && token ? (
        <ChartTransactions
          key={JSON.stringify(query)}
          token={token}
          query={query}
          kind={query.kind === "income" ? "income" : "spending"}
          filterLabel={selectedPoint?.label ?? null}
          onClearFilter={() => setSelected(null)}
          onOpen={onOpenSource}
        />
      ) : (
        !chart.query && (
          <button
            type="button"
            onClick={onOpenCashFlow}
            className="self-start text-xs text-signal underline decoration-dotted underline-offset-4 hover:text-signal-hi cursor-pointer"
          >
            See the income and spending behind this in Cash flow →
          </button>
        )
      )}
    </figure>
  );
}

/** The whole chart as one sentence, for screen readers. */
function describeChart(chart: ChartSpec): string {
  const points = chart.points
    .map((p) => {
      const share = p.share != null ? ` (${Math.round(p.share * 100)}%)` : "";
      return `${p.label} ${formatMoney(p.value)}${share}${p.partial ? " so far" : ""}`;
    })
    .join(", ");
  const change = chart.change
    ? `. ${chart.change.direction === "flat" ? "No change" : `${chart.change.direction === "up" ? "Up" : "Down"} ${formatMoney(Math.abs(chart.change.difference))}`}`
    : "";
  return `${chart.period ? `${chart.period}. ` : ""}${points}${change}.`;
}

function barColor(label: string): string {
  if (/^\d+ others$/.test(label)) return "var(--color-ink-faint)";
  return hasCategoryColor(label) ? colorForCategory(label) : "var(--color-signal)";
}

interface BarsProps {
  chart: ChartSpec;
  selected: number | null;
  onPick: (index: number) => void;
}

/** A bar that filters the list below when it has rows of its own. */
function PointButton({
  point,
  index,
  selected,
  onPick,
  className,
  children,
}: {
  point: ChartPoint;
  index: number;
  selected: number | null;
  onPick: (index: number) => void;
  className: string;
  children: ReactNode;
}) {
  const on = selected === index;
  const dim = selected !== null && !on;
  const summary = `${point.label}: ${formatMoney(point.value)}${point.share != null ? `, ${Math.round(point.share * 100)}%` : ""}${point.partial ? " so far" : ""}`;
  if (!point.query) {
    return (
      <div className={`${className} ${dim ? "opacity-40" : ""}`} aria-label={summary} role="img">
        {children}
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onPick(index)}
      aria-pressed={on}
      aria-label={`${summary}. ${on ? "Showing only these transactions" : "Show only these transactions"}`}
      className={`${className} cursor-pointer rounded-lg text-left transition-opacity hover:bg-surface ${dim ? "opacity-40" : ""} ${on ? "bg-surface" : ""}`}
    >
      {children}
    </button>
  );
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

function Breakdown({ chart, selected, onPick }: BarsProps) {
  const points = chart.points;
  const max = Math.max(...points.map((p) => p.value));
  return (
    <div role="group" aria-label={`${chart.title}, tap one to list its transactions`} className="-mx-2 flex flex-col gap-0.5">
      {points.map((p, i) => (
        <PointButton key={p.label} point={p} index={i} selected={selected} onPick={onPick} className="flex flex-col gap-1 px-2 py-1.5">
          <span className="flex w-full items-baseline justify-between gap-3 text-[13px]">
            <span className="truncate text-ink-soft">{p.label}</span>
            <span className="shrink-0 font-mono tabular-nums text-ink">
              {formatMoney(p.value)}
              {p.share != null && <span className="ml-2 text-ink-faint">{Math.round(p.share * 100)}%</span>}
            </span>
          </span>
          <Bar fraction={max ? p.value / max : 0} color={barColor(p.label)} />
        </PointButton>
      ))}
    </div>
  );
}

function Compare({ chart, selected, onPick }: BarsProps) {
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
      <div role="group" aria-label={`${chart.title}, tap one to list its transactions`} className="-mx-2 flex flex-col gap-0.5">
        {[
          { point: previous, color: "var(--color-line-strong)" },
          { point: current, color: "var(--color-signal)" },
        ].map(({ point, color }, i) => (
          <PointButton key={point.label} point={point} index={i} selected={selected} onPick={onPick} className="flex flex-col gap-1 px-2 py-1.5">
            <span className="flex w-full items-baseline justify-between gap-3 text-[13px]">
              <span className="text-ink-soft">{point.label}</span>
              <span className="font-mono tabular-nums text-ink">{formatMoney(point.value)}</span>
            </span>
            <Bar fraction={max ? point.value / max : 0} color={color} />
          </PointButton>
        ))}
      </div>
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

function Trend({ chart, selected, onPick }: BarsProps) {
  const points = chart.points;
  const max = Math.max(...points.map((p) => Math.abs(p.value))) || 1;
  const last = points[points.length - 1];
  return (
    <div className="flex flex-col gap-1.5">
      <div role="group" aria-label={`${chart.title}, tap a month to list its transactions`} className="flex h-28 items-end gap-2">
        {points.map((p, i) => {
          const isLast = i === points.length - 1;
          const color =
            p.value < 0 ? "var(--color-negative)" : isLast ? "var(--color-signal)" : "var(--color-line-strong)";
          return (
            <PointButton
              key={p.label + i}
              point={p}
              index={i}
              selected={selected}
              onPick={onPick}
              className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1"
            >
              {(isLast || selected === i) && (
                <span className="font-mono text-[11px] tabular-nums text-ink">{formatMoney(p.value)}</span>
              )}
              <span
                aria-hidden
                title={`${p.label}: ${formatMoney(p.value)}${p.partial ? " so far" : ""}`}
                className={`chart-rise block w-full max-w-10 rounded-t-md ${p.partial ? "opacity-70" : ""}`}
                style={{ height: `${Math.max((Math.abs(p.value) / max) * 100, 3)}%`, backgroundColor: color }}
              />
            </PointButton>
          );
        })}
      </div>
      <div aria-hidden className="flex gap-2">
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

const COLLAPSED_ROWS = 5;

/** The actual transactions a chart (or one tapped bar) is drawn from. */
function ChartTransactions({
  token,
  query,
  kind,
  filterLabel,
  onClearFilter,
  onOpen,
}: {
  token: string;
  query: SourceQuery;
  kind: "income" | "spending";
  filterLabel: string | null;
  onClearFilter: () => void;
  onOpen: (query: SourceQuery) => void;
}) {
  const [result, setResult] = useState<ItemizedTransactions | null>(null);
  const [failed, setFailed] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let stale = false;
    fetchQuery(token, query)
      .then((r) => !stale && setResult(r))
      .catch(() => !stale && setFailed(true));
    return () => {
      stale = true;
    };
  }, [token, query]);

  const items = result?.items ?? [];
  const shown = expanded ? items : items.slice(0, COLLAPSED_ROWS);

  return (
    <section aria-label={filterLabel ? `${filterLabel} transactions` : "Transactions behind this chart"} className="flex flex-col gap-1 border-t border-line pt-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-ink-soft">
          {filterLabel ?? "Every transaction"}
          {result && (
            <span className="text-ink-faint">
              {" "}· {result.transaction_count} {result.transaction_count === 1 ? "transaction" : "transactions"}
            </span>
          )}
        </span>
        {filterLabel && (
          <button
            type="button"
            onClick={onClearFilter}
            aria-label={`Show every transaction, not just ${filterLabel}`}
            className="min-h-8 shrink-0 rounded-full bg-signal-wash px-3 text-xs text-signal cursor-pointer"
          >
            {filterLabel} only ×
          </button>
        )}
      </div>

      {failed ? (
        <p className="py-2 text-xs text-ink-faint">Couldn't load the transactions. Open them in Transactions instead.</p>
      ) : !result ? (
        <div className="flex flex-col gap-2 py-1" aria-label="Loading transactions">
          <div className="h-4 animate-pulse rounded bg-surface" />
          <div className="h-4 animate-pulse rounded bg-surface" />
        </div>
      ) : items.length === 0 ? (
        <p className="py-2 text-xs text-ink-faint">No transactions in this window.</p>
      ) : (
        <ul className={`m-0 flex list-none flex-col p-0 ${expanded ? "max-h-72 overflow-y-auto" : ""}`}>
          {shown.map((item, i) => (
            <li key={i} className="flex min-h-11 items-center gap-3 border-t border-line text-[13px] first:border-t-0">
              <span
                aria-hidden
                className="h-2 w-2 shrink-0 rounded-sm"
                style={{ background: item.category && hasCategoryColor(item.category) ? colorForCategory(item.category) : "var(--color-ink-faint)" }}
              />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-ink">{item.merchant_name ?? item.category ?? "Transaction"}</span>
                <span className="font-mono text-[11px] text-ink-faint">
                  {formatDate(item.date)}
                  {item.category && ` · ${item.category}`}
                  {item.is_pending && " · Pending"}
                </span>
              </span>
              <RowAmount amount={item.amount} group={kind} />
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        {items.length > COLLAPSED_ROWS ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="min-h-11 text-[13px] text-signal hover:text-signal-hi cursor-pointer"
          >
            {expanded ? "Show fewer" : `Show all ${items.length}`}
          </button>
        ) : (
          <span />
        )}
        {kind === "spending" && (
          <button
            type="button"
            onClick={() => onOpen(query)}
            className="min-h-11 text-xs text-ink-soft underline decoration-dotted underline-offset-4 hover:text-ink cursor-pointer"
          >
            Open in Transactions →
          </button>
        )}
      </div>
    </section>
  );
}
