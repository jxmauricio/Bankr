import { useEffect, useRef, useState } from "react";
import { fetchInsights, markAllInsightsRead, markInsightRead, type Insight } from "../lib/api";
import { formatRelativeTime } from "../lib/format";

const TYPE_LABEL: Record<string, string> = {
  budget_overspend: "Budget",
  goal_drift: "Goal",
  unusual_transaction: "Unusual charge",
  price_change: "Price change",
};

/** Header bell: Bankr's nudges, newest first. Opening one marks it read and goes where it's about. */
export function InsightsBell({
  token,
  refreshKey,
  onOpenInsight,
}: {
  token: string;
  refreshKey?: unknown;
  onOpenInsight: (insight: Insight) => void;
}) {
  const [open, setOpen] = useState(false);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [unread, setUnread] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let stale = false;
    fetchInsights(token)
      .then((r) => {
        if (stale) return;
        setInsights(r.insights);
        setUnread(r.unread_count);
      })
      .catch(() => {});
    return () => {
      stale = true;
    };
  }, [token, refreshKey]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => !rootRef.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  function markRead(ids: string[]) {
    setInsights((list) => list.map((i) => (ids.includes(i.id) ? { ...i, read: true } : i)));
    setUnread((n) => Math.max(0, n - ids.length));
  }

  async function openInsight(insight: Insight) {
    setOpen(false);
    if (!insight.read) {
      markRead([insight.id]);
      markInsightRead(token, insight.id).catch(() => {});
    }
    onOpenInsight(insight);
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label={unread ? `Insights, ${unread} unread` : "Insights"}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="relative flex h-11 w-11 cursor-pointer items-center justify-center rounded-full text-ink-soft hover:bg-surface hover:text-ink"
      >
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute right-1.5 top-1.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-signal px-1 font-tabular text-[10px] font-semibold text-bg">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Insights"
          className="absolute right-0 top-12 z-50 flex max-h-[70vh] w-[min(360px,calc(100vw-32px))] flex-col overflow-hidden rounded-[20px] border border-line-strong bg-surface shadow-modal animate-drop"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <span className="text-sm font-semibold text-ink">Insights</span>
            {unread > 0 && (
              <button
                type="button"
                onClick={() => {
                  markRead(insights.map((i) => i.id));
                  setUnread(0);
                  markAllInsightsRead(token).catch(() => {});
                }}
                className="cursor-pointer text-xs text-signal hover:text-signal-hi"
              >
                Mark all read
              </button>
            )}
          </div>
          {insights.length === 0 ? (
            <p className="m-0 px-4 py-8 text-center text-[13px] text-ink-soft">
              Nothing yet. Bankr will flag budget overruns, price changes and unusual charges here.
            </p>
          ) : (
            <ul className="m-0 list-none overflow-y-auto p-0">
              {insights.map((i) => (
                <li key={i.id} className="border-t border-line first:border-0">
                  <button
                    type="button"
                    onClick={() => openInsight(i)}
                    className="flex w-full cursor-pointer gap-3 px-4 py-3 text-left hover:bg-raised"
                  >
                    <span aria-hidden className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${i.read ? "bg-transparent" : "bg-signal"}`} />
                    <span className="flex min-w-0 flex-col gap-0.5">
                      <span className="font-mono text-[10px] tracking-[0.1em] text-ink-faint">
                        {(TYPE_LABEL[i.type] ?? "Insight").toUpperCase()} · {formatRelativeTime(i.created_at)}
                      </span>
                      <span className={`text-[13px] ${i.read ? "text-ink-soft" : "text-ink"}`}>{i.message}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
