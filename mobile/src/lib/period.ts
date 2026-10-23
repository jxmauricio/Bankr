// Copied from web/src/lib/period.ts, minus localStorage persistence; the short
// labels are the mobile design's ("3 months", "Year").

/** The app-wide time filter: four fixed windows. */
export type Period = "this_month" | "last_month" | "last_3_months" | "last_year";

export const DEFAULT_PERIOD: Period = "this_month";

export const PERIODS: { value: Period; label: string; short: string; window: string }[] = [
  { value: "this_month", label: "This month", short: "This month", window: "this_month" },
  { value: "last_month", label: "Last month", short: "Last month", window: "last_month" },
  // Rolling 90 days, which is what the backend calls a three-month window.
  { value: "last_3_months", label: "Last 3 months", short: "3 months", window: "last_90_days" },
  { value: "last_year", label: "Last year", short: "Year", window: "last_year" },
];

export function periodInfo(period: Period) {
  return PERIODS.find((p) => p.value === period) ?? PERIODS[0];
}

/** The period picker's options, with the short labels that fit a phone. */
export const PERIOD_OPTIONS = PERIODS.map((p) => ({ value: p.value, label: p.short }));
