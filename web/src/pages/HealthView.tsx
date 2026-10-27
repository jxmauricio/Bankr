import { useEffect, useState } from "react";
import { fetchHealth, type HealthLine, type HealthTone, type SpendingHealth } from "../lib/api";
import { colorForCategory } from "../lib/chartColors";
import { formatMoney } from "../lib/format";
import type { TransactionFilter } from "./TransactionsView";

const TONE: Record<HealthTone, string> = {
  good: "text-positive",
  ok: "text-warn",
  high: "text-negative",
  neutral: "text-ink-soft",
};
const TONE_BG: Record<HealthTone, string> = {
  good: "bg-positive-soft",
  ok: "bg-warn-soft",
  high: "bg-negative-soft",
  neutral: "bg-raised",
};
const TONE_BAR: Record<HealthTone, string> = {
  good: "bg-positive",
  ok: "bg-warn",
  high: "bg-negative",
  neutral: "bg-ink-soft",
};

const pct = (n: number | null) => (n == null ? "—" : `${n.toFixed(n % 1 === 0 ? 0 : 1)}%`);
const whole = (n: number) => formatMoney(n).replace(/\.\d\d$/, "");

function badge(line: HealthLine): string {
  if (line.tone === "good") return "Healthy";
  if (line.tone === "ok") return line.higher_is_better ? "Low" : "A bit high";
  if (line.tone === "high") return line.higher_is_better ? "Too low" : "High";
  return "—";
}

export function HealthView({
  token,
  refreshKey,
  onOpenTransactions,
  onOpenCashFlow,
}: {
  token: string;
  refreshKey?: unknown;
  onOpenTransactions: (filter: TransactionFilter) => void;
  onOpenCashFlow: () => void;
}) {
  const [data, setData] = useState<SpendingHealth | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let stale = false;
    setData(null);
    setFailed(false);
    fetchHealth(token)
      .then((h) => !stale && setData(h))
      .catch(() => !stale && setFailed(true));
    return () => {
      stale = true;
    };
  }, [token, refreshKey]);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto animate-view">
      <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-4 px-4 py-4 lg:px-8 lg:py-6">
        <div className="flex flex-col gap-1">
          <h1 className="m-0 text-[22px] font-semibold tracking-[-0.02em] text-ink lg:text-[26px]">Health</h1>
          <span className="text-[13px] text-ink-soft">
            {data
              ? data.partial
                ? `This month so far · ${data.label}, scaled to a full month.`
                : `Average of the last ${data.months_used} complete month${data.months_used === 1 ? "" : "s"} · ${data.label}.`
              : "Average spending as a share of income, next to widely cited guidelines."}
          </span>
        </div>

        {failed ? (
          <div className="card p-4">
            <p className="py-10 text-center text-sm text-ink-soft">Couldn’t load spending health. Switch views to try again.</p>
          </div>
        ) : !data ? (
          <div className="h-[420px] animate-pulse card" aria-label="Loading spending health" />
        ) : data.income <= 0 ? (
          <div className="card p-4">
            <p className="py-10 text-center text-sm text-ink-soft">
              No income in linked accounts for {data.label}, so there’s nothing to score against.
            </p>
          </div>
        ) : (
          <>
            <div className="grid gap-3 md:grid-cols-3">
              {data.snapshots.map((s) => (
                <SnapshotCard
                  key={s.id}
                  line={s}
                  onClick={() => (s.id === "saved" ? onOpenCashFlow() : onOpenTransactions({ category: s.name, query: "" }))}
                />
              ))}
            </div>

            <SplitBar buckets={data.buckets} />

            <section className="card px-3.5 py-2 md:px-5 md:py-3">
              <div className="flex items-baseline justify-between gap-3 px-1 py-3">
                <h2 className="m-0 text-[15px] font-semibold text-ink">By category</h2>
                <span className="font-mono text-[11px] text-ink-faint">
                  of {whole(data.income)}/mo income
                </span>
              </div>
              <ul>
                {data.categories.map((c, i) => (
                  <CategoryRow
                    key={c.id}
                    line={c}
                    first={i === 0}
                    onClick={() => onOpenTransactions({ category: c.name, query: "" })}
                  />
                ))}
              </ul>
            </section>

            <p className="px-1 text-[12px] leading-relaxed text-ink-faint">{data.note}</p>
          </>
        )}
      </div>
    </div>
  );
}

function SnapshotCard({ line, onClick }: { line: HealthLine; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex cursor-pointer flex-col gap-2 card p-4 text-left ring-1 ring-transparent hover:ring-line-strong"
    >
      <span className="flex items-center justify-between gap-2">
        <span className="text-[13px] text-ink-soft">{line.id === "saved" ? "Saving" : line.name === "Rent & Utilities" ? "Rent" : line.name}</span>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${TONE_BG[line.tone]} ${TONE[line.tone]}`}>
          {badge(line)}
        </span>
      </span>
      <span className={`font-mono text-[28px] font-medium tracking-[-0.03em] ${TONE[line.tone]}`}>{pct(line.pct)}</span>
      <span className="font-mono text-[13px] text-ink">{whole(line.amount)}/mo</span>
      <span className="text-[12px] leading-snug text-ink-soft">{line.verdict}</span>
      {line.source && <span className="text-[11px] text-ink-faint">{line.source}{line.recommended_pct != null ? ` · ${line.recommended_pct}%` : ""}</span>}
    </button>
  );
}

function SplitBar({ buckets }: { buckets: HealthLine[] }) {
  const [needs, wants, saved] = buckets;
  const parts = [
    { ...needs, color: "var(--color-spend)" },
    { ...wants, color: "var(--color-warn)" },
    { ...saved, color: "var(--color-positive)" },
  ];
  const total = Math.max(parts.reduce((s, p) => s + Math.max(p.amount, 0), 0), 1);
  return (
    <section className="flex flex-col gap-3 card p-4 md:p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="m-0 text-[15px] font-semibold text-ink">50 / 30 / 20</h2>
        <span className="text-[12px] text-ink-faint">Needs · wants · saved</span>
      </div>
      <div className="flex h-3.5 overflow-hidden rounded">
        {parts.map((p) => (
          <div
            key={p.id}
            title={`${p.name} ${pct(p.pct)}`}
            style={{ width: `${(Math.max(p.amount, 0) / total) * 100}%`, background: p.color }}
          />
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {parts.map((p) => (
          <div key={p.id} className="flex items-baseline justify-between gap-2 text-[13px]">
            <span className="text-ink-soft">
              {p.name} <span className="text-ink-faint">({p.recommended_pct}%)</span>
            </span>
            <span className={`font-mono ${TONE[p.tone]}`}>
              {pct(p.pct)} · {whole(p.amount)}
            </span>
          </div>
        ))}
      </div>
      <p className="m-0 text-[12px] leading-relaxed text-ink-faint">{needs.why}</p>
    </section>
  );
}

function CategoryRow({ line, first, onClick }: { line: HealthLine; first: boolean; onClick: () => void }) {
  const rec = line.recommended_pct;
  const actual = line.pct ?? 0;
  const scale = Math.max(rec ?? 0, actual, 20);
  return (
    <li className={first ? "" : "border-t border-line"}>
      <button type="button" onClick={onClick} className="flex w-full cursor-pointer flex-col gap-1.5 py-3 text-left hover:bg-raised/60">
        <span className="flex items-baseline gap-2">
          <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: colorForCategory(line.name) }} />
          <span className="flex-1 truncate text-sm text-ink">{line.name}</span>
          <span className="font-mono text-[13px] text-ink">{whole(line.amount)}</span>
          <span className={`w-14 text-right font-mono text-[13px] ${TONE[line.tone]}`}>{pct(line.pct)}</span>
        </span>
        <span className="relative ml-4 block h-1.5 rounded-full bg-line">
          <span
            className={`absolute inset-y-0 left-0 rounded-full ${TONE_BAR[line.tone]}`}
            style={{ width: `${Math.min((actual / scale) * 100, 100)}%` }}
          />
          {rec != null && (
            <span
              className="absolute top-[-3px] h-3 w-0.5 rounded-full bg-ink-faint"
              style={{ left: `${Math.min((rec / scale) * 100, 100)}%` }}
              title={`Guideline ${rec}%`}
            />
          )}
        </span>
        <span className="ml-4 text-[12px] text-ink-soft">
          {line.verdict}
          {rec != null && ` · ${line.source}`}
          {line.this_month_pct != null && ` · this month ${pct(line.this_month_pct)}`}
        </span>
      </button>
    </li>
  );
}
