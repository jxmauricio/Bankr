/** The Home screen's global time filter: four fixed windows. */
export type Period = "this_month" | "last_month" | "last_3_months" | "last_year";

export const DEFAULT_PERIOD: Period = "this_month";

export const PERIODS: { value: Period; label: string; short: string; window: string }[] = [
  { value: "this_month", label: "This month", short: "This month", window: "this_month" },
  { value: "last_month", label: "Last month", short: "Last month", window: "last_month" },
  // Rolling 90 days, which is what the backend calls a three-month window.
  { value: "last_3_months", label: "Last 3 months", short: "Last 3 months", window: "last_90_days" },
  { value: "last_year", label: "Last year", short: "Last year", window: "last_year" },
];

const KEY = "bankr:period";

export function periodInfo(period: Period) {
  return PERIODS.find((p) => p.value === period) ?? PERIODS[0];
}

export function loadPeriod(): Period {
  try {
    const raw = localStorage.getItem(KEY);
    if (PERIODS.some((p) => p.value === raw)) return raw as Period;
  } catch {
    // Storage unavailable: fall back to the default.
  }
  return DEFAULT_PERIOD;
}

export function savePeriod(period: Period) {
  try {
    localStorage.setItem(KEY, period);
  } catch {
    // Not worth surfacing; the filter just won't be remembered.
  }
}

type Point = { date: string; net_worth: number };

/** Net worth snapshots that fall inside [start, end] (YYYY-MM-DD, inclusive). */
export function windowHistory(history: Point[], start?: string, end?: string): Point[] {
  if (!start || !end) return [];
  return history.filter((p) => p.date >= start && p.date <= end);
}
