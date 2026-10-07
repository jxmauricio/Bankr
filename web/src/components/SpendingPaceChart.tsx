import { useEffect, useState, type PointerEvent } from "react";
import { fetchSpendingPace, type SpendingPace } from "../lib/api";

const whole = (n: number) => "$" + Math.round(n).toLocaleString("en-US");

/** Rounded-up axis max with a step that gives 4–6 gridlines. */
function niceMax(value: number): { max: number; step: number } {
  const raw = Math.max(value, 100) / 5;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  return { max: Math.ceil(value / step) * step || step, step };
}

/**
 * Where this month ends up if the last week's everyday pace holds. One-off
 * big days (rent, a flight) are left out of the pace, since they won't repeat.
 */
function project(running: number[], daysInMonth: number): number[] {
  const today = running.length;
  const daily = running.map((v, i) => v - (i ? running[i - 1] : 0));
  const positive = daily.filter((d) => d > 0).sort((a, b) => a - b);
  const median = positive.length ? positive[Math.floor(positive.length / 2)] : 0;
  const recent = daily.slice(Math.max(0, today - 7)).filter((d) => d <= median * 3);
  const per = recent.length ? recent.reduce((s, d) => s + Math.max(d, 0), 0) / recent.length : 0;
  const out = [running[today - 1] ?? 0];
  for (let d = today + 1; d <= daysInMonth; d++) out.push(out[out.length - 1] + per);
  return out;
}

interface Geometry {
  W: number;
  H: number;
  padL: number;
  padB: number;
}

const WIDE: Geometry = { W: 712, H: 300, padL: 44, padB: 28 };
const COMPACT: Geometry = { W: 326, H: 150, padL: 0, padB: 14 };

/**
 * Spending this month vs last month, as running totals by day of month.
 * Hover or tap a day to compare the two at that point.
 */
export function SpendingPaceChart({ token, refreshKey }: { token: string; refreshKey?: unknown }) {
  const [pace, setPace] = useState<SpendingPace | null>(null);
  const [failed, setFailed] = useState(false);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    let stale = false;
    setFailed(false);
    fetchSpendingPace(token)
      .then((p) => !stale && setPace(p))
      .catch(() => !stale && setFailed(true));
    return () => {
      stale = true;
    };
  }, [token, refreshKey]);

  if (failed) return null;
  if (!pace) return <div className="h-[200px] animate-pulse rounded-3xl bg-surface" aria-label="Loading spending chart" />;

  const thisRun = pace.this_month.running;
  const lastRun = pace.last_month.running;
  const today = thisRun.length;
  if (today === 0) return null;
  const days = Math.max(pace.this_month.days_in_month, pace.last_month.days_in_month);
  const proj = project(thisRun, pace.this_month.days_in_month);
  const projEnd = proj[proj.length - 1];
  const lastAt = (d: number) => lastRun[Math.min(d, lastRun.length) - 1] ?? 0;
  const lastTotal = lastRun[lastRun.length - 1] ?? 0;
  const { max, step } = niceMax(Math.max(lastTotal, projEnd, thisRun[today - 1]) * 1.05);

  const day = Math.min(hover ?? today, today);
  const thisV = thisRun[day - 1];
  const lastV = lastAt(day);
  const diff = thisV - lastV;
  const less = diff <= 0;
  const headDiff = thisRun[today - 1] - lastAt(today);
  const headLess = headDiff <= 0;
  const hasLast = lastTotal > 0;

  const insight = !hasLast
    ? `At this pace you'll finish ${pace.this_month.label} near ${whole(projEnd)}.`
    : headLess
      ? `You've spent ${whole(-headDiff)} less than last month at the same point. At this pace you'll finish near ${whole(projEnd)}${projEnd < lastTotal ? ` — about ${whole(lastTotal - projEnd)} under last month` : ""}.`
      : `You've spent ${whole(headDiff)} more than last month at the same point. At this pace you'll finish near ${whole(projEnd)}.`;
  const aria = `Running spending total. ${pace.this_month.label}: ${whole(thisRun[today - 1])} by day ${today}. ${pace.last_month.label} by day ${today}: ${whole(lastAt(today))}, and ${whole(lastTotal)} in all. Projected: about ${whole(projEnd)}.`;

  function build(g: Geometry) {
    const x = (d: number) => g.padL + ((d - 1) / (days - 1)) * (g.W - g.padL);
    const y = (v: number) => g.H - g.padB - (v / max) * (g.H - g.padB - 8);
    const path = (vals: number[], from = 1) => vals.map((v, i) => `${i ? "L" : "M"}${x(from + i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
    const lineThis = path(thisRun);
    return {
      x,
      y,
      lineThis,
      areaThis: `${lineThis} L${x(today).toFixed(1)} ${y(0)} L${x(1)} ${y(0)} Z`,
      lineLast: path(lastRun),
      lineProj: path(proj, today),
      grid: Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step),
    };
  }

  function pickDay(e: PointerEvent<SVGSVGElement>, g: Geometry) {
    const rect = e.currentTarget.getBoundingClientRect();
    const vx = ((e.clientX - rect.left) / rect.width) * g.W;
    const d = Math.round(((vx - g.padL) / (g.W - g.padL)) * (days - 1)) + 1;
    setHover(Math.max(1, Math.min(today, d)));
  }

  const w = build(WIDE);
  const m = build(COMPACT);
  const deltaClass = headLess ? "text-positive bg-positive-soft" : "text-negative bg-negative-soft";
  const tipLeftPct = Math.min(Math.max((w.x(day) + 14) / WIDE.W, 0), 1 - 200 / WIDE.W) * 100;

  const legend = (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-soft md:text-xs">
      <span className="flex items-center gap-1.5">
        <span className="h-[3px] w-[18px] rounded-sm bg-spend" />
        This month
      </span>
      {hasLast && (
        <span className="flex items-center gap-1.5">
          <span className="w-[18px] border-t-2 border-dashed border-ink-soft" />
          Last month
        </span>
      )}
      <span className="flex items-center gap-1.5">
        <span className="w-[18px] border-t-2 border-dotted border-spend" />
        Projected
      </span>
    </div>
  );

  return (
    <section aria-label="Spending this month compared with last month" className="flex flex-col gap-4 rounded-3xl bg-surface p-4 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-semibold text-ink-soft">
            Spending this month <span className="font-normal text-ink-faint">· {pace.this_month.label}</span>
          </span>
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="font-tabular text-[28px] font-medium tracking-[-0.04em] text-ink md:text-4xl">{whole(thisRun[today - 1])}</span>
            {hasLast && (
              <span className={`rounded-full px-2.5 py-1 font-tabular text-xs font-medium md:text-[13px] ${deltaClass}`}>
                {headLess ? "▼" : "▲"} {whole(Math.abs(headDiff))} vs last month by day {today}
              </span>
            )}
          </div>
          <span className="font-tabular text-xs text-ink-faint">
            {pace.this_month.days_in_month - today} days left · projected ~{whole(projEnd)}
            {hasLast && ` · last month ended at ${whole(lastTotal)}`}
          </span>
        </div>
        <div className="hidden flex-col items-end gap-2.5 md:flex">
          {legend}
          <span className="font-tabular text-[11px] text-ink-faint">Running total by day of month</span>
        </div>
      </div>

      {/* Wide */}
      <div className="relative hidden md:block">
        <svg
          role="img"
          aria-label={aria}
          viewBox={`0 0 ${WIDE.W} ${WIDE.H}`}
          className="block h-auto w-full cursor-crosshair overflow-visible touch-none"
          onPointerMove={(e) => pickDay(e, WIDE)}
          onPointerDown={(e) => pickDay(e, WIDE)}
        >
          {w.grid.map((v) => (
            <g key={v}>
              <line x1={WIDE.padL} x2={WIDE.W} y1={w.y(v)} y2={w.y(v)} stroke="var(--color-line)" />
              <text x={WIDE.padL - 8} y={w.y(v) + 4} textAnchor="end" fontFamily="JetBrains Mono, monospace" fontSize="11" fill="var(--color-ink-faint)">
                {v >= 1000 ? `$${v / 1000}k` : `$${v}`}
              </text>
            </g>
          ))}
          {[1, 8, 15, 22, days].map((d) => (
            <text key={d} x={w.x(d)} y={WIDE.H - 8} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="11" fill="var(--color-ink-faint)">
              {d === 1 ? "Day 1" : d}
            </text>
          ))}
          <path d={w.areaThis} fill="var(--color-spend)" opacity="0.12" />
          {hasLast && <path d={w.lineLast} fill="none" stroke="var(--color-ink-soft)" strokeWidth="1.75" strokeDasharray="5 5" strokeLinejoin="round" />}
          <path d={w.lineProj} fill="none" stroke="var(--color-spend)" strokeWidth="2" strokeDasharray="1 5" strokeLinecap="round" opacity="0.9" />
          <path d={w.lineThis} fill="none" stroke="var(--color-spend)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
          <line x1={w.x(day)} x2={w.x(day)} y1="8" y2={WIDE.H - WIDE.padB} stroke="var(--color-line-strong)" />
          {hasLast && (
            <>
              <path d={`M${w.x(day)} ${w.y(thisV)} L${w.x(day)} ${w.y(lastV)}`} stroke={less ? "var(--color-positive)" : "var(--color-negative)"} strokeWidth="2" />
              <circle cx={w.x(day)} cy={w.y(lastV)} r="4" fill="var(--color-surface)" stroke="var(--color-ink-soft)" strokeWidth="2" />
            </>
          )}
          <circle cx={w.x(day)} cy={w.y(thisV)} r="5" fill="var(--color-spend)" stroke="var(--color-surface)" strokeWidth="2" />
        </svg>
        <div
          role="status"
          aria-live="polite"
          className="pointer-events-none absolute top-2 flex w-[196px] flex-col gap-1.5 rounded-[14px] border border-line-strong bg-raised px-3 py-2.5 shadow-menu"
          style={{ left: `${tipLeftPct}%` }}
        >
          <span className="font-tabular text-[11px] text-ink-faint">{hover && hover !== today ? `Day ${day}` : `Today · day ${day}`}</span>
          <div className="flex justify-between text-xs">
            <span className="text-spend">This month</span>
            <span className="font-tabular text-ink">{whole(thisV)}</span>
          </div>
          {hasLast && (
            <>
              <div className="flex justify-between text-xs">
                <span className="text-ink-soft">Last month</span>
                <span className="font-tabular text-ink">{whole(lastV)}</span>
              </div>
              <div className="flex justify-between border-t border-line-strong pt-1.5 text-xs">
                <span className="text-ink-soft">Difference</span>
                <span className={`font-tabular ${less ? "text-positive" : "text-negative"}`}>
                  {less ? "−" : "+"}
                  {whole(Math.abs(diff))}
                </span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Compact */}
      <svg role="img" aria-label={aria} viewBox={`0 0 ${COMPACT.W} ${COMPACT.H}`} className="block h-auto w-full overflow-visible md:hidden">
        {m.grid
          .filter((_, i) => i % 2 === 0)
          .map((v) => (
            <line key={v} x1="0" x2={COMPACT.W} y1={m.y(v)} y2={m.y(v)} stroke="var(--color-line)" />
          ))}
        <path d={m.areaThis} fill="var(--color-spend)" opacity="0.12" />
        {hasLast && <path d={m.lineLast} fill="none" stroke="var(--color-ink-soft)" strokeWidth="1.5" strokeDasharray="4 4" />}
        <path d={m.lineProj} fill="none" stroke="var(--color-spend)" strokeWidth="2" strokeDasharray="1 4" strokeLinecap="round" />
        <path d={m.lineThis} fill="none" stroke="var(--color-spend)" strokeWidth="2.25" strokeLinejoin="round" />
        <line x1={m.x(today)} x2={m.x(today)} y1="0" y2={COMPACT.H - COMPACT.padB} stroke="var(--color-line-strong)" />
        {hasLast && <circle cx={m.x(today)} cy={m.y(lastAt(today))} r="3.5" fill="var(--color-surface)" stroke="var(--color-ink-soft)" strokeWidth="1.75" />}
        <circle cx={m.x(today)} cy={m.y(thisRun[today - 1])} r="4.5" fill="var(--color-spend)" stroke="var(--color-surface)" strokeWidth="2" />
        <text x="0" y={COMPACT.H - 1} fontFamily="JetBrains Mono, monospace" fontSize="10" fill="var(--color-ink-faint)">1</text>
        <text x={m.x(today)} y={COMPACT.H - 1} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="10" fill="var(--color-ink-soft)">Today</text>
        <text x={COMPACT.W} y={COMPACT.H - 1} textAnchor="end" fontFamily="JetBrains Mono, monospace" fontSize="10" fill="var(--color-ink-faint)">{days}</text>
      </svg>
      <div className="md:hidden">{legend}</div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
        <span className="text-[13px] leading-normal text-ink-soft">{insight}</span>
        {hover !== null && hover !== today && (
          <button type="button" onClick={() => setHover(null)} className="hidden h-10 shrink-0 cursor-pointer rounded-xl bg-raised px-3.5 text-[13px] text-ink md:block">
            Back to today
          </button>
        )}
      </div>
    </section>
  );
}

