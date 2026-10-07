import { useEffect, useState, type ReactNode } from "react";
import { fetchQuery, type ChartPoint, type ChartSpec, type ItemizedTransactions, type SourceQuery } from "../lib/api";
import { colorForCategory, hasCategoryColor } from "../lib/chartColors";
import { formatDate, formatMoney } from "../lib/format";
import { RowAmount } from "./TransactionSearch";

/** The one picture under a chat reply. The numbers are built server-side from
 * a fresh query (tools.show_chart, services/answer_charts.py), never written
 * by the model, so they always match the dashboard. Each kind answers one
 * shape of question: where it went (breakdown), then vs now (compare), how
 * it moved (trend), day by day (daily), one merchant over time (merchant),
 * what's coming up (recurring) and what moved net worth (net_worth).
 *
 * Every chart is described in full for screen readers and comes with the
 * transactions it's drawn from: tap a bar or row to list only its rows. */
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
  const props = { chart, selected, onPick: pick };
  const rowsByPoint = chart.points.some((p) => p.query);

  return (
    <figure className="m-0 flex w-full max-w-[560px] flex-col gap-3 rounded-2xl bg-raised p-4">
      <figcaption className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-ink">{chart.title}</span>
        {chart.period && <span className="shrink-0 font-mono text-[11px] text-ink-faint">{chart.period}</span>}
        <span className="sr-only">: {describeChart(chart)}</span>
      </figcaption>
      {chart.kind === "breakdown" && <Breakdown {...props} />}
      {chart.kind === "compare" && <Compare {...props} />}
      {chart.kind === "trend" && <Trend {...props} />}
      {chart.kind === "daily" && <Daily {...props} />}
      {chart.kind === "merchant" && <Merchant {...props} />}
      {chart.kind === "recurring" && <Recurring {...props} />}
      {chart.kind === "net_worth" && <NetWorth {...props} />}
      {query && token ? (
        <ChartTransactions
          key={JSON.stringify(query)}
          token={token}
          query={query}
          kind={query.kind === "income" ? "income" : query.kind === "all" ? "all" : "spending"}
          filterLabel={selectedPoint?.label ?? null}
          onClearFilter={() => setSelected(null)}
          onOpen={onOpenSource}
        />
      ) : rowsByPoint ? (
        <p className="m-0 border-t border-line pt-3 text-xs text-ink-faint">
          {chart.kind === "recurring" ? "Tap one to see its past payments." : "Tap an account to see its transactions."}
        </p>
      ) : (
        <button
          type="button"
          onClick={onOpenCashFlow}
          className="self-start text-xs text-signal underline decoration-dotted underline-offset-4 hover:text-signal-hi cursor-pointer"
        >
          See the income and spending behind this in Cash flow →
        </button>
      )}
    </figure>
  );
}

/** The answer's headline, at the top of the reply bubble: the range, one big
 * number, one line of context ("$3,610.00 across 7 categories"). */
export function AnswerHeadline({ headline }: { headline: NonNullable<ChartSpec["headline"]> }) {
  const tone = headline.tone === "pos" ? "text-positive" : headline.tone === "neg" ? "text-negative" : "text-ink";
  const sign = headline.tone === "pos" && headline.value > 0 ? "+" : headline.tone === "neg" && headline.value < 0 ? "−" : "";
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[11px] tracking-[0.1em] text-ink-faint">{headline.eyebrow}</span>
      <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span className={`font-mono text-[30px] font-medium leading-tight tracking-[-0.04em] tabular-nums sm:text-[34px] ${tone}`}>
          {sign}
          {formatMoney(Math.abs(headline.value))}
        </span>
        {headline.detail && <span className="text-sm text-ink-soft">{headline.detail}</span>}
      </span>
    </div>
  );
}

/** The whole chart as one sentence, for screen readers. */
function describeChart(chart: ChartSpec): string {
  const points = chart.points
    .map((p) => {
      const share = p.share != null ? ` (${Math.round(p.share * 100)}%)` : "";
      const before = p.previous != null ? `, ${formatMoney(p.previous)} ${chart.previous_label ?? "before"}` : "";
      const next = p.next_date ? `, next ${formatDate(p.next_date)}` : "";
      return `${p.label} ${formatMoney(p.value)}${share}${p.partial ? " so far" : ""}${before}${next}`;
    })
    .join(", ");
  const change = chart.change
    ? `. ${chart.change.direction === "flat" ? "No change" : `${chart.change.direction === "up" ? "Up" : "Down"} ${formatMoney(Math.abs(chart.change.difference))}`}`
    : "";
  const average = chart.average != null ? `. Average ${formatMoney(chart.average)} a month` : "";
  return `${chart.period ? `${chart.period}. ` : ""}${points}${change}${average}.`;
}

function barColor(label: string): string {
  if (/^\d+ others$/.test(label)) return "var(--color-ink-faint)";
  return hasCategoryColor(label) ? colorForCategory(label) : "var(--color-signal)";
}

/** "$71", "$2.1k" -- for labels on narrow bars. */
function shortMoney(value: number): string {
  const abs = Math.abs(value);
  return abs >= 1000 ? `$${(abs / 1000).toFixed(1)}k` : `$${Math.round(abs)}`;
}

interface BarsProps {
  chart: ChartSpec;
  selected: number | null;
  onPick: (index: number) => void;
}

function pointSummary(point: ChartPoint): string {
  const share = point.share != null ? `, ${Math.round(point.share * 100)}%` : "";
  return `${point.label}: ${formatMoney(point.value)}${share}${point.partial ? " so far" : ""}`;
}

/** A bar that filters the list below when it has rows of its own. */
function PointButton({
  point,
  index,
  selected,
  onPick,
  className,
  summary,
  children,
}: {
  point: ChartPoint;
  index: number;
  selected: number | null;
  onPick: (index: number) => void;
  className: string;
  summary?: string;
  children: ReactNode;
}) {
  const on = selected === index;
  const dim = selected !== null && !on;
  const label = summary ?? pointSummary(point);
  if (!point.query) {
    return (
      <div className={`${className} ${dim ? "opacity-40" : ""}`} aria-label={label} role="img">
        {children}
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onPick(index)}
      aria-pressed={on}
      aria-label={`${label}. ${on ? "Showing only these transactions" : "Show only these transactions"}`}
      className={`${className} cursor-pointer rounded-lg text-left transition-opacity hover:bg-surface ${dim ? "opacity-40" : ""} ${on ? "bg-surface" : ""}`}
    >
      {children}
    </button>
  );
}

function Bar({ fraction, color }: { fraction: number; color: string }) {
  return (
    <span className="block h-2 w-full overflow-hidden rounded-full bg-line">
      <span
        className="chart-grow block h-full rounded-full"
        style={{ width: `${Math.max(fraction * 100, 2)}%`, backgroundColor: color }}
      />
    </span>
  );
}

// --- where it went ------------------------------------------------------------

function Change({ value, previous }: { value: number; previous: number }) {
  const diff = value - previous;
  if (Math.abs(diff) < 0.5) return <span className="text-ink-faint">same</span>;
  // Spending more is the bad direction.
  return diff > 0 ? (
    <span className="text-negative">▲ {shortMoney(diff)}</span>
  ) : (
    <span className="text-positive">▼ {shortMoney(diff)}</span>
  );
}

function Breakdown({ chart, selected, onPick }: BarsProps) {
  const points = chart.points;
  const max = Math.max(...points.map((p) => p.value));
  const hasPrevious = points.some((p) => p.previous != null);
  return (
    <div className="flex flex-col gap-2">
      <div aria-hidden className="flex h-3.5 gap-0.5 overflow-hidden rounded">
        {points.map((p) => (
          <span key={p.label} style={{ width: `${(p.share ?? 0) * 100}%`, background: barColor(p.label) }} />
        ))}
      </div>
      {hasPrevious && (
        <div aria-hidden className="grid grid-cols-[1fr_auto_5.5rem] gap-3 px-2 pt-1 font-mono text-[10px] tracking-[0.08em] text-ink-faint">
          <span>CATEGORY</span>
          <span className="text-right">{(chart.previous_label ?? "vs before").toUpperCase()}</span>
          <span className="text-right">AMOUNT</span>
        </div>
      )}
      <div role="group" aria-label={`${chart.title}, tap one to list its transactions`} className="-mx-2 flex flex-col">
        {points.map((p, i) => (
          <PointButton
            key={p.label}
            point={p}
            index={i}
            selected={selected}
            onPick={onPick}
            summary={`${pointSummary(p)}${p.previous != null ? `, ${formatMoney(p.previous)} ${chart.previous_label ?? "before"}` : ""}`}
            className="flex flex-col gap-1.5 border-t border-line px-2 py-2 first:border-t-0"
          >
            <span className="grid w-full grid-cols-[1fr_auto_5.5rem] items-baseline gap-3 text-[13px]">
              <span className="flex min-w-0 items-center gap-2">
                <span aria-hidden className="h-2 w-2 shrink-0 rounded-sm" style={{ background: barColor(p.label) }} />
                <span className="truncate text-ink-soft">{p.label}</span>
              </span>
              <span className="text-right font-mono text-xs tabular-nums">
                {p.previous != null ? <Change value={p.value} previous={p.previous} /> : p.share != null ? (
                  <span className="text-ink-faint">{Math.round(p.share * 100)}%</span>
                ) : null}
              </span>
              <span className="text-right font-mono tabular-nums text-ink">{formatMoney(p.value)}</span>
            </span>
            <Bar fraction={max ? p.value / max : 0} color={barColor(p.label)} />
          </PointButton>
        ))}
      </div>
    </div>
  );
}

// --- then vs now --------------------------------------------------------------

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

// --- columns: months, days, one merchant -----------------------------------------

/** Vertical bars along a baseline. A bar far above the rest (rent day) is
 * capped and drawn with a break, so the small ones stay readable. */
function Columns({
  chart,
  selected,
  onPick,
  label,
  valueLabel,
  barColorFor,
  average,
  height = "h-28",
}: BarsProps & {
  label: (p: ChartPoint) => string;
  valueLabel: (p: ChartPoint, i: number) => string | null;
  barColorFor: (p: ChartPoint, i: number) => string;
  average?: number | null;
  height?: string;
}) {
  const points = chart.points;
  const values = points.map((p) => Math.abs(p.value));
  const sorted = [...values].sort((a, b) => b - a);
  // Cap at 1.25x the second-biggest when the biggest is over 3x it.
  const cap = sorted.length > 2 && sorted[1] > 0 && sorted[0] > sorted[1] * 3 ? sorted[1] * 1.25 : sorted[0] || 1;
  const many = points.length > 14;
  return (
    <div className="flex flex-col gap-1.5">
      <div role="group" aria-label={`${chart.title}, tap one to list its transactions`} className={`relative flex ${height} items-end ${many ? "gap-0.5" : "gap-1.5"} border-b border-line-strong`}>
        {average != null && average > 0 && average < cap && (
          <span aria-hidden className="pointer-events-none absolute inset-x-0 z-10 border-t border-dashed border-ink-faint/70" style={{ bottom: `${(average / cap) * 100}%` }}>
            <span className="absolute -top-4 right-0 bg-raised px-1 font-mono text-[10px] text-ink-soft">avg {shortMoney(average)}</span>
          </span>
        )}
        {points.map((p, i) => {
          const broken = Math.abs(p.value) > cap;
          const text = valueLabel(p, i);
          return (
            <PointButton
              key={p.label + i}
              point={p}
              index={i}
              selected={selected}
              onPick={onPick}
              className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1"
            >
              {text && !many && <span className="font-mono text-[10px] tabular-nums text-ink-soft">{text}</span>}
              <span
                aria-hidden
                className={`chart-rise relative block w-full max-w-10 rounded-t-md ${p.partial ? "border border-b-0 border-dashed" : ""}`}
                style={{
                  height: `${Math.max((Math.min(Math.abs(p.value), cap) / cap) * 100, p.value ? 4 : 1.5)}%`,
                  backgroundColor: p.partial ? "transparent" : barColorFor(p, i),
                  // The in-progress month is drawn as an outline, in the series color.
                  borderColor: p.partial ? "var(--color-spend)" : barColorFor(p, i),
                }}
              >
                {broken && <span className="absolute inset-x-0 top-2 h-1 -skew-y-12 bg-raised" />}
              </span>
            </PointButton>
          );
        })}
      </div>
      <div aria-hidden className={`flex ${many ? "gap-0.5" : "gap-1.5"}`}>
        {points.map((p, i) => (
          <span
            key={p.label + i}
            className={`min-w-0 flex-1 truncate text-center font-mono text-[10px] ${selected === i ? "text-ink" : "text-ink-faint"}`}
          >
            {many && i % 7 !== 0 && i !== points.length - 1 ? "" : label(p)}
            {p.partial && "*"}
          </span>
        ))}
      </div>
      {points.some((p) => p.partial) && <span className="font-mono text-[11px] text-ink-faint">* so far</span>}
    </div>
  );
}

function Trend(props: BarsProps) {
  const points = props.chart.points;
  return (
    <Columns
      {...props}
      label={(p) => p.label}
      valueLabel={(p, i) => (i === points.length - 1 || props.selected === i ? shortMoney(p.value) : null)}
      barColorFor={(p, i) =>
        p.value < 0 ? "var(--color-negative)" : i === points.length - 1 ? "var(--color-signal)" : "var(--color-line-strong)"
      }
    />
  );
}

function Daily(props: BarsProps) {
  return (
    <Columns
      {...props}
      height="h-24"
      label={(p) => `${p.weekday ?? ""} ${p.label.split(" ")[1] ?? p.label}`.trim()}
      valueLabel={(p) => (p.value ? shortMoney(p.value) : null)}
      barColorFor={(_, i) => (props.selected === i ? "var(--color-ink)" : "var(--color-spend)")}
    />
  );
}

function Merchant(props: BarsProps) {
  const { chart } = props;
  const peak = Math.max(...chart.points.map((p) => p.value));
  return (
    <div className="flex flex-col gap-3">
      <Columns
        {...props}
        label={(p) => p.label}
        valueLabel={(p) => (p.value === peak ? shortMoney(p.value) : null)}
        barColorFor={(p) => (p.value === peak ? "var(--color-spend)" : "var(--color-line-strong)")}
        average={chart.average}
      />
      {chart.stats && chart.stats.length > 0 && (
        <dl className="m-0 grid grid-cols-3 gap-2">
          {chart.stats.map((s) => (
            <div key={s.label} className="rounded-xl bg-surface px-3 py-2.5">
              <dt className="text-[11px] text-ink-soft">{s.label}</dt>
              <dd className="m-0 font-mono text-[15px] tabular-nums text-ink">
                {s.unit === "usd" ? formatMoney(s.value) : s.value}
                {s.date && <span className="ml-1 text-[11px] text-ink-faint">{formatDate(s.date)}</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

// --- what's coming up ------------------------------------------------------------

function Recurring({ chart, selected, onPick }: BarsProps) {
  const today = chart.today ? new Date(`${chart.today}T00:00`) : null;
  const horizon = chart.horizon ? new Date(`${chart.horizon}T00:00`) : null;
  const span = today && horizon ? horizon.getTime() - today.getTime() : 0;
  const upcoming = chart.upcoming ?? [];
  return (
    <div className="flex flex-col gap-3">
      {span > 0 && (
        <div
          role="img"
          aria-label={`Upcoming charges: ${upcoming.map((u) => `${u.label} ${formatDate(u.date)} ${formatMoney(u.value)}`).join(", ") || "none in the next 30 days"}`}
          className="relative h-16"
        >
          <span className="absolute inset-x-0 top-1/2 h-px bg-line-strong" />
          <span className="absolute left-0 top-1/2 h-3 w-px -translate-y-1/2 bg-ink-soft" />
          <span className="absolute bottom-0 left-0 font-mono text-[10px] text-ink-soft">Today</span>
          <span className="absolute bottom-0 right-0 font-mono text-[10px] text-ink-faint">{formatDate(chart.horizon!)}</span>
          {upcoming.map((u, i) => {
            const at = ((new Date(`${u.date}T00:00`).getTime() - today!.getTime()) / span) * 100;
            const up = i % 2 === 0;
            return (
              <span key={u.label + u.date} className="absolute top-1/2" style={{ left: `${Math.min(Math.max(at, 1), 99)}%` }}>
                <span className="absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-signal ring-2 ring-raised" />
                <span
                  className={`absolute -translate-x-1/2 whitespace-nowrap font-mono text-[10px] text-ink-soft ${up ? "-top-6" : "top-2.5"}`}
                >
                  {shortMoney(u.value)}
                </span>
              </span>
            );
          })}
        </div>
      )}
      <div role="group" aria-label={`${chart.title}, tap one to see its past payments`} className="-mx-2 flex flex-col">
        <div aria-hidden className="grid grid-cols-[1fr_4rem_5rem] gap-3 px-2 pb-1 font-mono text-[10px] tracking-[0.08em] text-ink-faint">
          <span>SERVICE</span>
          <span className="text-right">NEXT</span>
          <span className="text-right">MONTHLY</span>
        </div>
        {chart.points.map((p, i) => (
          <PointButton
            key={p.label}
            point={p}
            index={i}
            selected={selected}
            onPick={onPick}
            summary={`${p.label}: ${formatMoney(p.value)} a month, next ${p.next_date ? formatDate(p.next_date) : "unknown"}${p.price_changed ? `, price changed from ${formatMoney(p.typical_amount ?? 0)} to ${formatMoney(p.last_amount ?? 0)}` : ""}${p.suggested ? ", not confirmed yet" : ""}`}
            className="grid min-h-11 grid-cols-[1fr_4rem_5rem] items-center gap-3 border-t border-line px-2 text-[13px]"
          >
            <span className="flex min-w-0 flex-wrap items-center gap-x-2">
              <span className="truncate text-ink">{p.label}</span>
              {p.price_changed && (
                <span className="rounded-full bg-warn-soft px-2 py-0.5 text-[10px] font-medium text-warn">Price up</span>
              )}
              {p.suggested && <span className="text-[10px] text-ink-faint">Suggested</span>}
            </span>
            <span className="text-right font-mono text-xs tabular-nums text-ink-soft">{p.next_date ? formatDate(p.next_date) : "—"}</span>
            <span className="text-right font-mono tabular-nums text-ink">{formatMoney(p.value)}</span>
          </PointButton>
        ))}
      </div>
      <span className="text-xs leading-relaxed text-ink-faint">
        Next dates are estimated from past charges. Bankr can't cancel subscriptions — this list is to help you decide.
      </span>
    </div>
  );
}

// --- what moved net worth ----------------------------------------------------------

function NetWorth({ chart, selected, onPick }: BarsProps) {
  const points = chart.points;
  const gains = Math.max(0, ...points.map((p) => p.value));
  const drags = Math.max(0, ...points.map((p) => -p.value));
  const range = gains + drags || 1;
  const zero = (drags / range) * 100;
  const net = points.reduce((sum, p) => sum + p.value, 0);
  return (
    <div className="flex flex-col gap-1">
      <div role="group" aria-label={`${chart.title}, tap an account to see its transactions`} className="-mx-2 flex flex-col">
        {points.map((p, i) => {
          const width = (Math.abs(p.value) / range) * 100;
          const positive = p.value >= 0;
          return (
            <PointButton
              key={p.label}
              point={p}
              index={i}
              selected={selected}
              onPick={onPick}
              summary={`${p.label}: ${positive ? "up" : "down"} ${formatMoney(Math.abs(p.value))}`}
              className="grid min-h-10 grid-cols-[minmax(0,8.5rem)_1fr_5.5rem] items-center gap-3 px-2"
            >
              <span className={`truncate text-[13px] ${p.note ? "italic text-ink-soft" : "text-ink"}`}>{p.label}</span>
              <span className="relative h-5">
                <span className="absolute inset-y-0 w-px bg-line-strong" style={{ left: `${zero}%` }} />
                <span
                  className={`chart-grow absolute top-0.5 h-4 ${positive ? "rounded-r" : "rounded-l"} ${p.note ? "opacity-60" : ""}`}
                  style={{
                    left: positive ? `${zero}%` : `${zero - width}%`,
                    width: `${Math.max(width, 1)}%`,
                    background: positive ? "var(--color-positive)" : "var(--color-negative)",
                  }}
                />
              </span>
              <span className={`text-right font-mono text-xs tabular-nums ${positive ? "text-positive" : "text-negative"}`}>
                {positive ? "+" : "−"}
                {formatMoney(Math.abs(p.value))}
              </span>
            </PointButton>
          );
        })}
      </div>
      <div className="-mx-2 grid grid-cols-[minmax(0,8.5rem)_1fr_5.5rem] gap-3 border-t border-line-strong px-2 pt-2">
        <span className="text-[13px] font-semibold text-ink">Net change</span>
        <span />
        <span className={`text-right font-mono text-sm tabular-nums ${net >= 0 ? "text-positive" : "text-negative"}`}>
          {net >= 0 ? "+" : "−"}
          {formatMoney(Math.abs(net))}
        </span>
      </div>
      <span className="mt-1 text-xs leading-relaxed text-ink-faint">
        Each account's change is the sum of its transactions. Investment growth and interest Bankr can't see line by
        line show as “Not from transactions”.
      </span>
    </div>
  );
}

// --- the rows behind it -------------------------------------------------------------

const COLLAPSED_ROWS = 5;

type Grouping = "date" | "category";

/** The actual transactions a chart (or one tapped bar) is drawn from, by
 * date or by category. */
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
  kind: "income" | "spending" | "all";
  filterLabel: string | null;
  onClearFilter: () => void;
  onOpen: (query: SourceQuery) => void;
}) {
  const [result, setResult] = useState<ItemizedTransactions | null>(null);
  const [failed, setFailed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [grouping, setGrouping] = useState<Grouping>("date");

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
  const groups = groupItems(items, grouping, expanded ? Infinity : COLLAPSED_ROWS);
  const amountGroup = kind === "income" ? "income" : "spending";

  return (
    <section aria-label={filterLabel ? `${filterLabel} transactions` : "Transactions behind this chart"} className="flex flex-col gap-1 border-t border-line pt-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-ink-soft">
          {filterLabel ?? "Every transaction"}
          {result && (
            <span className="text-ink-faint">
              {" "}· {result.transaction_count} {result.transaction_count === 1 ? "transaction" : "transactions"}
            </span>
          )}
        </span>
        <div className="flex items-center gap-2">
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
          {items.length > 1 && (
            <div role="tablist" aria-label="Group by" className="flex rounded-full bg-surface p-0.5 text-[11px]">
              {(["date", "category"] as const).map((g) => (
                <button
                  key={g}
                  type="button"
                  role="tab"
                  aria-selected={grouping === g}
                  onClick={() => setGrouping(g)}
                  className={`min-h-7 rounded-full px-2.5 transition-colors cursor-pointer ${
                    grouping === g ? "bg-line-strong text-ink" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  By {g}
                </button>
              ))}
            </div>
          )}
        </div>
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
        <div className={`flex flex-col ${expanded ? "max-h-80 overflow-y-auto pr-1" : ""}`}>
          {groups.map((group) => (
            <div key={group.title}>
              <div className="flex justify-between pb-0.5 pt-2.5 font-mono text-[10px] tracking-[0.06em] text-ink-faint">
                <span>{group.title}</span>
                <span className="tabular-nums">{formatMoney(Math.abs(group.total))}</span>
              </div>
              <ul className="m-0 flex list-none flex-col p-0">
                {group.items.map((item, i) => (
                  <li key={i} className="flex min-h-11 items-center gap-3 border-t border-line text-[13px]">
                    <span
                      aria-hidden
                      className="h-2 w-2 shrink-0 rounded-sm"
                      style={{ background: item.category && hasCategoryColor(item.category) ? colorForCategory(item.category) : "var(--color-ink-faint)" }}
                    />
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-ink">{item.merchant_name ?? item.category ?? "Transaction"}</span>
                      <span className="font-mono text-[11px] text-ink-faint">
                        {grouping === "date" ? item.category ?? "Uncategorized" : formatDate(item.date)}
                        {item.is_pending && " · Pending"}
                      </span>
                    </span>
                    {kind === "all" ? (
                      <span className={`font-tabular shrink-0 pl-3 ${item.amount > 0 ? "text-positive" : "text-ink"}`}>
                        {item.amount > 0 ? "+" : "−"}
                        {formatMoney(Math.abs(item.amount))}
                      </span>
                    ) : (
                      <RowAmount amount={item.amount} group={amountGroup} />
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
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

/** Rows grouped by day (newest first) or by category (biggest first), keeping
 * at most `limit` rows across all groups. */
function groupItems(items: ItemizedTransactions["items"], grouping: Grouping, limit: number) {
  const groups: { title: string; total: number; items: ItemizedTransactions["items"] }[] = [];
  const byKey = new Map<string, (typeof groups)[number]>();
  for (const item of items) {
    const key = grouping === "date" ? item.date : item.category ?? "Uncategorized";
    let group = byKey.get(key);
    if (!group) {
      const title =
        grouping === "date"
          ? new Date(`${item.date}T00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }).toUpperCase()
          : key.toUpperCase();
      group = { title, total: 0, items: [] };
      byKey.set(key, group);
      groups.push(group);
    }
    group.total += item.amount;
    group.items.push(item);
  }
  if (grouping === "category") groups.sort((a, b) => Math.abs(b.total) - Math.abs(a.total));
  let left = limit;
  const shown = [];
  for (const group of groups) {
    if (left <= 0) break;
    shown.push({ ...group, items: group.items.slice(0, left) });
    left -= group.items.length;
  }
  return shown;
}
