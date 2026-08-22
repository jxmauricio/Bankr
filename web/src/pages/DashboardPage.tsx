import { useEffect, useState } from "react";
import {
  fetchGoalProgress,
  fetchIncome,
  fetchNetWorth,
  fetchRollup,
  fetchSpending,
  type GoalProgress,
  type ItemizedTransactions,
  type NetWorthHistory,
  type PeriodRollup,
} from "../lib/api";
import { useSession } from "../lib/session";
import { formatDate, formatMoney } from "../lib/format";
import { GoalPaceTrack } from "../components/GoalPaceTrack";
import { ChatPanel } from "../components/ChatPanel";

type Period = "week" | "month" | "year";
type Tab = "spending" | "income";

export function DashboardPage() {
  const { token, signOut } = useSession();
  const [period, setPeriod] = useState<Period>("month");
  const [tab, setTab] = useState<Tab>("spending");
  const [netWorth, setNetWorth] = useState<NetWorthHistory | null>(null);
  const [goalProgress, setGoalProgress] = useState<GoalProgress | null>(null);
  const [rollup, setRollup] = useState<PeriodRollup | null>(null);
  const [itemized, setItemized] = useState<ItemizedTransactions | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetchNetWorth(token).then(setNetWorth);
    fetchGoalProgress(token).then(setGoalProgress);
  }, [token]);

  useEffect(() => {
    if (!token) return;
    fetchRollup(token, period).then(setRollup);
    (tab === "spending" ? fetchSpending(token, period) : fetchIncome(token, period)).then(setItemized);
  }, [token, period, tab]);

  return (
    <div className="min-h-screen pb-24">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <span className="font-display text-xl font-semibold text-ink">Bankr</span>
        <button
          type="button"
          onClick={signOut}
          className="text-sm text-ink-soft transition-colors hover:text-ink cursor-pointer"
        >
          Sign out
        </button>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <section className="mb-6 rounded-xl border border-border bg-surface p-6">
          <span className="text-sm font-medium text-ink-soft">Net worth</span>
          <div className="mt-1 font-tabular text-4xl font-semibold text-ink">
            {netWorth?.current !== null && netWorth?.current !== undefined ? formatMoney(netWorth.current) : "—"}
          </div>
        </section>

        {goalProgress && goalProgress.type && (
          <section className="mb-6">
            <GoalPaceTrack progress={goalProgress} />
          </section>
        )}

        <div className="mb-4 flex justify-end">
          <div className="flex rounded-full border border-border bg-surface p-1 text-sm">
            {(["week", "month", "year"] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPeriod(p)}
                className={`rounded-full px-3.5 py-1 capitalize transition-colors cursor-pointer ${
                  period === p ? "bg-accent text-white" : "text-ink-soft hover:text-ink"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <section className="rounded-xl border border-border bg-surface p-5">
            <h2 className="mb-4 text-sm font-medium text-ink-soft capitalize">{period} summary</h2>
            {rollup ? (
              <div className="space-y-2.5">
                <Row label="Income" value={rollup.income} />
                <Row label="Spending" value={-rollup.spending} />
                <div className="my-1 border-t border-border" />
                <Row label="Saved" value={rollup.gain} emphasize />
              </div>
            ) : (
              <SkeletonLines />
            )}
          </section>

          <section className="rounded-xl border border-border bg-surface p-5">
            <div className="mb-4 flex rounded-full bg-bg p-1 text-sm">
              {(["spending", "income"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={`flex-1 rounded-full py-1 capitalize transition-colors cursor-pointer ${
                    tab === t ? "bg-surface text-ink shadow-sm" : "text-ink-soft"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            {itemized ? (
              itemized.items.length === 0 ? (
                <p className="py-6 text-center text-sm text-ink-faint">Nothing here yet for this period.</p>
              ) : (
                <ul className="max-h-80 space-y-1 overflow-y-auto">
                  {itemized.items.map((item, i) => (
                    <li key={i} className="flex items-center justify-between py-1.5 text-sm">
                      <div className="min-w-0">
                        <div className="truncate text-ink">{item.merchant_name ?? item.category ?? "Transaction"}</div>
                        <div className="text-xs text-ink-faint">
                          {formatDate(item.date)} {item.category && `· ${item.category}`}
                          {item.is_pending && " · Pending"}
                        </div>
                      </div>
                      <span className="font-tabular shrink-0 pl-3 text-ink">{formatMoney(Math.abs(item.amount))}</span>
                    </li>
                  ))}
                </ul>
              )
            ) : (
              <SkeletonLines />
            )}
          </section>
        </div>
      </main>

      <button
        type="button"
        onClick={() => setChatOpen(true)}
        className="fixed bottom-6 right-6 flex items-center gap-2 rounded-full bg-accent px-5 py-3 font-medium text-white shadow-lg transition-transform hover:scale-105 cursor-pointer"
      >
        <SparkleIcon />
        Ask Bankr
      </button>

      <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}

function Row({ label, value, emphasize }: { label: string; value: number; emphasize?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-ink-soft">{label}</span>
      <span className={`font-tabular ${emphasize ? "font-semibold text-accent-strong" : "text-ink"}`}>
        {formatMoney(value)}
      </span>
    </div>
  );
}

function SkeletonLines() {
  return (
    <div className="space-y-2.5">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-bg" />
      ))}
    </div>
  );
}

function SparkleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2l1.8 5.6L19.4 9.4 13.8 11.2 12 16.8l-1.8-5.6L4.6 9.4 10.2 7.6 12 2z" />
    </svg>
  );
}
