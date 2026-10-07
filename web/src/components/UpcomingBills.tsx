import { useEffect, useState } from "react";
import { fetchRecurring, type RecurringOverview } from "../lib/api";
import { formatMoney } from "../lib/format";

const WEEK_MS = 7 * 86_400_000;

/** Money rail line: bills due in the next 7 days. Opens Plan. */
export function UpcomingBills({
  token,
  refreshKey,
  version,
  onOpen,
}: {
  token: string;
  refreshKey?: unknown;
  /** Bump to refetch after a change elsewhere. */
  version?: number;
  onOpen: () => void;
}) {
  const [data, setData] = useState<RecurringOverview | null>(null);

  useEffect(() => {
    let stale = false;
    fetchRecurring(token)
      .then((d) => !stale && setData(d))
      .catch(() => {});
    return () => {
      stale = true;
    };
  }, [token, refreshKey, version]);

  if (!data) return null;
  const [y, m, d] = data.today.split("-").map(Number);
  const weekEnd = new Date(y, m - 1, d).getTime() + WEEK_MS;
  const due = data.upcoming.filter((u) => {
    const [uy, um, ud] = u.date.split("-").map(Number);
    return u.kind !== "income" && u.status === "confirmed" && new Date(uy, um - 1, ud).getTime() <= weekEnd;
  });
  if (!due.length && !data.suggested_count) return null;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full cursor-pointer flex-col gap-1 rounded-[20px] bg-surface p-4 text-left hover:bg-raised"
    >
      <span className="font-mono text-[11px] tracking-[0.12em] text-ink-faint">BILLS THIS WEEK</span>
      {due.length ? (
        <span className="text-sm text-ink">
          <span className="font-tabular font-semibold">{formatMoney(due.reduce((s, u) => s + u.amount, 0))}</span>
          <span className="text-ink-soft">
            {" "}
            · {due.length} due{due.length <= 2 ? `: ${due.map((u) => u.name).join(", ")}` : ""}
          </span>
        </span>
      ) : (
        <span className="text-sm text-ink-soft">Nothing due.</span>
      )}
      {data.suggested_count > 0 && (
        <span className="text-xs text-signal">
          {data.suggested_count} recurring charge{data.suggested_count === 1 ? "" : "s"} to review →
        </span>
      )}
    </button>
  );
}
