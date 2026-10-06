import { useEffect, useState } from "react";
import { fetchRollupWindow, type PeriodRollup } from "./api";
import { periodInfo, type Period } from "./period";

/** Income, spending and left over for the header's period. `refreshKey`
 * refetches after a bank refresh. */
export function useCashFlow(token: string | null, period: Period, refreshKey?: unknown): PeriodRollup | null {
  const [flow, setFlow] = useState<PeriodRollup | null>(null);
  const window = periodInfo(period).window;

  useEffect(() => {
    if (!token) return;
    let stale = false;
    fetchRollupWindow(token, window)
      .then((r) => !stale && setFlow(r))
      .catch(() => !stale && setFlow(null));
    return () => {
      stale = true;
    };
  }, [token, window, refreshKey]);

  return flow;
}
