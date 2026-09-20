export function formatMoney(amount: number): string {
  const sign = amount < 0 ? "-" : "";
  return `${sign}$${Math.abs(amount).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** For a full ISO datetime (unlike formatDate's plain "YYYY-MM-DD"), e.g.
 * conversation timestamps -- "3m ago", "5h ago", "2d ago", then falls back
 * to a plain date past a week out. */
export function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffMin = Math.round(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export const GOAL_KINDS = ["save", "track_spending"] as const;

export const GOAL_KIND_LABELS: Record<string, string> = {
  save: "Savings goal",
  track_spending: "Spending tracker",
};

export const GOAL_KIND_HINTS: Record<string, string> = {
  save: "Put money toward something — a trip, a cushion, paying off debt.",
  track_spending: "Watch a category over a week, month, or other window — optionally with a cap.",
};

/** Title chips for a savings goal. These are names, not types. */
export const SAVE_NAME_SUGGESTIONS = ["Paying off debt", "Savings goals", "Emergency fund"] as const;

export const SPEND_CATEGORIES = [
  "Groceries",
  "Dining",
  "Restaurants",
  "Fast Food",
  "Coffee",
  "Alcohol & Bars",
  "Transportation",
  "Gas",
  "Rideshare & Taxi",
  "Public Transit",
  "Parking & Tolls",
  "Auto Maintenance",
  "Travel",
  "Rent & Housing",
  "Utilities",
  "Subscriptions",
  "Entertainment",
  "Shopping",
  "Health",
  "Loan Payments",
  "Fees",
  "Other",
] as const;

export const TRACKING_WINDOWS: { id: string; label: string }[] = [
  { id: "this_week", label: "This week" },
  { id: "this_month", label: "This month" },
  { id: "this_year", label: "This year" },
  { id: "last_7_days", label: "Last 7 days" },
  { id: "last_30_days", label: "Last 30 days" },
  { id: "last_90_days", label: "Last 90 days" },
];

/** One row of a spending or income list. Spending rows are stored as
 * negative (money out); a positive spending row is a refund, and must read
 * as money back -- the list has to visibly add up to the net total above it. */
export function describeRowAmount(amount: number, group: "income" | "spending"): { text: string; isCredit: boolean } {
  if (group === "spending" && amount > 0) return { text: `+${formatMoney(amount)}`, isCredit: true };
  return { text: formatMoney(Math.abs(amount)), isCredit: false };
}
