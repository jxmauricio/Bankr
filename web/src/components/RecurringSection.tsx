import { useEffect, useState, type ReactNode } from "react";
import {
  ApiError,
  fetchRecurring,
  updateRecurring,
  type RecurringOverview,
  type RecurringSeries,
  type RecurringStatus,
} from "../lib/api";
import { formatMoney } from "../lib/format";

const CADENCE_LABEL: Record<RecurringSeries["cadence"], string> = {
  weekly: "Weekly",
  biweekly: "Every 2 weeks",
  monthly: "Monthly",
  quarterly: "Every 3 months",
  yearly: "Yearly",
};

const KIND_LABEL = { bill: "Bill", subscription: "Subscription", income: "Income" } as const;

function dayLabel(iso: string, today: string): string {
  if (iso === today) return "Today";
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const [ty, tm, td] = today.split("-").map(Number);
  const diff = Math.round((date.getTime() - new Date(ty, tm - 1, td).getTime()) / 86_400_000);
  if (diff === 1) return "Tomorrow";
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

/** Recurring bills, subscriptions and paychecks: review what Bankr found, then see what's coming. */
export function RecurringSection({
  token,
  refreshKey,
  focus,
  onChanged,
}: {
  token: string;
  refreshKey?: unknown;
  /** A series was confirmed, dismissed or retyped. */
  onChanged?: () => void;
  /** Scroll here and highlight it (e.g. from a price-change insight). */
  focus?: boolean;
}) {
  const [data, setData] = useState<RecurringOverview | null>(null);
  const [failed, setFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let stale = false;
    fetchRecurring(token)
      .then((d) => {
        if (stale) return;
        setData(d);
        setFailed(false);
      })
      .catch(() => !stale && setFailed(true));
    return () => {
      stale = true;
    };
  }, [token, refreshKey]);

  async function setStatus(series: RecurringSeries, status: RecurringStatus) {
    setBusyId(series.id);
    setError(null);
    try {
      await updateRecurring(token, series.id, { status });
      setData(await fetchRecurring(token));
      onChanged?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that. Try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function setKind(series: RecurringSeries, kind: RecurringSeries["kind"]) {
    setBusyId(series.id);
    try {
      await updateRecurring(token, series.id, { kind });
      setData(await fetchRecurring(token));
      onChanged?.();
    } finally {
      setBusyId(null);
    }
  }

  if (failed) {
    return <Shell focus={focus}><p className="py-6 text-center text-sm text-ink-soft">Couldn’t load recurring charges.</p></Shell>;
  }
  if (!data) return <div className="h-[260px] animate-pulse rounded-3xl bg-surface" aria-label="Loading recurring charges" />;

  const active = data.series.filter((s) => s.is_active);
  const suggested = active.filter((s) => s.status === "suggested");
  const confirmed = active.filter((s) => s.status === "confirmed");
  const upcoming = data.upcoming.filter((u) => u.kind !== "income");
  const upcomingShown = showAll ? upcoming : upcoming.slice(0, 6);
  const upcomingTotal = upcoming.reduce((s, u) => s + u.amount, 0);

  return (
    <Shell focus={focus}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2 className="m-0 text-lg font-semibold text-ink">Recurring</h2>
          <span className="text-[13px] text-ink-soft">Bills, subscriptions and paychecks Bankr found in your history.</span>
        </div>
        <div className="flex gap-4 font-tabular text-xs text-ink-soft">
          <span>
            Subscriptions <span className="text-ink">{formatMoney(data.monthly.subscriptions)}</span>/mo
          </span>
          <span>
            Bills <span className="text-ink">{formatMoney(data.monthly.bills)}</span>/mo
          </span>
        </div>
      </div>

      {suggested.length > 0 && (
        <div className="flex flex-col gap-2 rounded-[18px] border border-signal/30 bg-signal-wash p-3.5">
          <span className="text-[13px] font-semibold text-ink">
            Review {suggested.length} we found
            <span className="font-normal text-ink-soft"> — confirm the ones that really repeat.</span>
          </span>
          {suggested.map((s) => (
            <div key={s.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2 first-of-type:border-0">
              <span className="min-w-0 text-[13px] text-ink">
                {s.name}
                <span className="text-ink-soft">
                  {" "}
                  · {CADENCE_LABEL[s.cadence]} · {formatMoney(s.last_amount)} · {s.occurrences} times
                </span>
              </span>
              <span className="flex gap-1.5">
                <button
                  type="button"
                  disabled={busyId === s.id}
                  onClick={() => setStatus(s, "confirmed")}
                  className="h-9 cursor-pointer rounded-lg bg-signal px-3 text-xs font-semibold text-bg hover:bg-signal-hi disabled:opacity-60"
                >
                  Confirm
                </button>
                <button
                  type="button"
                  disabled={busyId === s.id}
                  onClick={() => setStatus(s, "dismissed")}
                  className="h-9 cursor-pointer rounded-lg px-3 text-xs text-ink-soft hover:text-ink disabled:opacity-60"
                >
                  Not recurring
                </button>
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          <span className="flex items-baseline justify-between text-[13px] font-semibold text-ink">
            Next 30 days
            <span className="font-tabular text-xs font-normal text-ink-soft">{formatMoney(upcomingTotal)}</span>
          </span>
          {upcoming.length === 0 ? (
            <p className="m-0 text-xs text-ink-faint">Nothing expected. Confirm recurring charges above to see them here.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col p-0">
              {upcomingShown.map((u, i) => (
                <li key={`${u.series_id}-${u.date}-${i}`} className="flex items-center justify-between gap-3 border-t border-line py-2 first:border-0">
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate text-[13px] text-ink">
                      {u.name}
                      {u.status === "suggested" && <span className="text-xs text-ink-faint"> · unconfirmed</span>}
                    </span>
                    <span className="font-tabular text-[11px] text-ink-faint">{dayLabel(u.date, data.today)}</span>
                  </span>
                  <span className="shrink-0 font-tabular text-[13px] text-ink">{formatMoney(u.amount)}</span>
                </li>
              ))}
            </ul>
          )}
          {upcoming.length > 6 && (
            <button type="button" onClick={() => setShowAll((v) => !v)} className="self-start cursor-pointer text-xs text-signal hover:text-signal-hi">
              {showAll ? "Show less" : `Show all ${upcoming.length}`}
            </button>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-[13px] font-semibold text-ink">Confirmed</span>
          {confirmed.length === 0 ? (
            <p className="m-0 text-xs text-ink-faint">None yet.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col p-0">
              {confirmed.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-3 border-t border-line py-2 first:border-0">
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate text-[13px] text-ink">{s.name}</span>
                    <span className="text-[11px] text-ink-faint">
                      {CADENCE_LABEL[s.cadence]}
                      {s.price_changed && (
                        <span className="text-warn">
                          {" "}
                          · was {formatMoney(s.typical_amount)}
                        </span>
                      )}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <select
                      aria-label={`Type of ${s.name}`}
                      value={s.kind}
                      disabled={busyId === s.id}
                      onChange={(e) => setKind(s, e.target.value as RecurringSeries["kind"])}
                      className="h-8 cursor-pointer rounded-lg border border-line bg-raised px-1.5 text-xs text-ink-soft"
                    >
                      {Object.entries(KIND_LABEL).map(([k, label]) => (
                        <option key={k} value={k}>
                          {label}
                        </option>
                      ))}
                    </select>
                    <span className="w-[72px] text-right font-tabular text-[13px] text-ink">{formatMoney(s.last_amount)}</span>
                    <button
                      type="button"
                      aria-label={`Stop tracking ${s.name}`}
                      disabled={busyId === s.id}
                      onClick={() => setStatus(s, "dismissed")}
                      className="h-8 w-8 cursor-pointer rounded-lg text-ink-faint hover:text-ink"
                    >
                      ✕
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      {error && <p className="m-0 text-xs text-negative">{error}</p>}
    </Shell>
  );
}

function Shell({ children, focus }: { children: ReactNode; focus?: boolean }) {
  return (
    <section
      id="recurring"
      ref={(el) => {
        if (focus && el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      }}
      className={`flex flex-col gap-4 rounded-3xl bg-surface p-4 md:px-7 md:py-6 ${focus ? "ring-1 ring-signal/40" : ""}`}
    >
      {children}
    </section>
  );
}
