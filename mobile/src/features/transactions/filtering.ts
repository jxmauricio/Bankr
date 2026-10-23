import type { TransactionRow } from "@/lib/api";
import { accountLabel, merchantOf, topCategories } from "@/lib/transactions";

// Everything the Transactions filters do to a fetched list. The date range is
// the only filter the backend applies; the rest narrows the rows here, the way
// the web TransactionsView does.

export type DateFilter = { kind: "preset"; window: string } | { kind: "custom"; start: string; end: string };
export type Direction = "all" | "out" | "in";
export type QuickId = "pending" | "refunds" | "over100" | "uncategorized";

export interface Filters {
  date: DateFilter;
  query: string;
  categories: string[];
  accountIds: string[];
  direction: Direction;
  quick: QuickId[];
}

export const DEFAULT_FILTERS: Filters = {
  date: { kind: "preset", window: "this_month" },
  query: "",
  categories: [],
  accountIds: [],
  direction: "all",
  quick: [],
};

/** True when anything differs from the defaults, so a reset would change something. */
export function isFiltered(f: Filters): boolean {
  return (
    f.date.kind !== "preset" ||
    f.date.window !== "this_month" ||
    f.query.trim() !== "" ||
    f.categories.length > 0 ||
    f.accountIds.length > 0 ||
    f.direction !== "all" ||
    f.quick.length > 0
  );
}

// --- dates ------------------------------------------------------------------

/** YYYY-MM-DD in local time. */
export function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function parseIso(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** The date sheet's presets, in order. `window` is the backend's window name. */
export const DATE_PRESETS: { window: string; label: string }[] = [
  { window: "this_month", label: "This month" },
  { window: "last_month", label: "Last month" },
  { window: "last_30_days", label: "Last 30 days" },
  { window: "last_90_days", label: "Last 3 months" },
  { window: "this_year", label: "This year" },
];

// Windows other screens can hand over (Cash flow's "Last year") but the sheet doesn't list.
const OTHER_WINDOW_LABELS: Record<string, string> = { last_year: "Last year" };

/** The days a named window covers, matching backend money_query.resolve_window. */
export function windowRange(window: string, today = new Date()): { start: string; end: string } {
  const y = today.getFullYear();
  const m = today.getMonth();
  const back = (days: number) => iso(new Date(y, m, today.getDate() - days));
  switch (window) {
    case "last_month":
      return { start: iso(new Date(y, m - 1, 1)), end: iso(new Date(y, m, 0)) };
    case "last_30_days":
      return { start: back(29), end: iso(today) };
    case "last_90_days":
      return { start: back(89), end: iso(today) };
    case "this_year":
      return { start: iso(new Date(y, 0, 1)), end: iso(today) };
    case "last_year":
      return { start: iso(new Date(y - 1, 0, 1)), end: iso(new Date(y - 1, 11, 31)) };
    default:
      return { start: iso(new Date(y, m, 1)), end: iso(today) };
  }
}

function shortDate(s: string, withYear: boolean): string {
  return parseIso(s).toLocaleDateString("en-US", withYear ? { month: "short", day: "numeric", year: "numeric" } : { month: "short", day: "numeric" });
}

/** "Oct 1 – Oct 16", with the year only when it isn't this year. */
export function rangeLabel(start: string, end: string): string {
  const thisYear = String(new Date().getFullYear());
  const withYear = !start.startsWith(thisYear) || !end.startsWith(thisYear);
  return start === end ? shortDate(start, withYear) : `${shortDate(start, withYear)} – ${shortDate(end, withYear)}`;
}

/** What the Date chip says. */
export function dateLabel(date: DateFilter): string {
  if (date.kind === "custom") return rangeLabel(date.start, date.end);
  return DATE_PRESETS.find((p) => p.window === date.window)?.label ?? OTHER_WINDOW_LABELS[date.window] ?? "This month";
}

// --- rows -------------------------------------------------------------------

/** Rows that count toward money in/out totals (the web view's rule). */
export function counts(t: TransactionRow): boolean {
  return !t.is_excluded && t.category_type !== "transfer";
}

export const QUICK_FILTERS: { id: QuickId; label: string; test: (t: TransactionRow) => boolean }[] = [
  { id: "pending", label: "Pending", test: (t) => t.is_pending },
  // Money back on a spending category; income and transfers in aren't refunds.
  { id: "refunds", label: "Refunds", test: (t) => t.amount > 0 && t.category_type === "expense" },
  { id: "over100", label: "Over $100", test: (t) => Math.abs(t.amount) > 100 },
  { id: "uncategorized", label: "Uncategorized", test: (t) => !t.is_split && !t.category && !t.parent_category },
];

export function applyFilters(rows: TransactionRow[], f: Filters): TransactionRow[] {
  const q = f.query.trim().toLowerCase();
  const quick = QUICK_FILTERS.filter((x) => f.quick.includes(x.id));
  return rows.filter(
    (t) =>
      (f.categories.length === 0 || topCategories(t).some((c) => f.categories.includes(c))) &&
      (f.accountIds.length === 0 || f.accountIds.includes(t.account.id)) &&
      (f.direction === "all" || (f.direction === "in" ? t.amount > 0 : t.amount < 0)) &&
      quick.every((x) => x.test(t)) &&
      (!q ||
        merchantOf(t).toLowerCase().includes(q) ||
        (t.category ?? "").toLowerCase().includes(q) ||
        (t.notes ?? "").toLowerCase().includes(q) ||
        Math.abs(t.amount).toFixed(2).includes(q))
  );
}

/** Money out and in across the shown rows, transfers and excluded rows aside. */
export function summarize(rows: TransactionRow[]): { count: number; out: number; in: number } {
  let out = 0;
  let inn = 0;
  for (const t of rows) {
    if (!counts(t)) continue;
    if (t.amount < 0) out -= t.amount;
    else inn += t.amount;
  }
  return { count: rows.length, out, in: inn };
}

export interface DayGroup {
  title: string;
  /** Money out that day, for the header; 0 when none. */
  out: number;
  data: TransactionRow[];
}

/** Newest day first, each with what went out that day. */
export function groupByDay(rows: TransactionRow[]): DayGroup[] {
  const byDay = new Map<string, TransactionRow[]>();
  for (const row of rows) {
    const day = byDay.get(row.date);
    if (day) day.push(row);
    else byDay.set(row.date, [row]);
  }
  const today = iso(new Date());
  return [...byDay.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, data]) => ({
      title: date === today ? "Today" : shortDate(date, !date.startsWith(today.slice(0, 4))),
      out: summarize(data).out,
      data,
    }));
}

/** Each top-level category in the rows, with its count and money out, biggest first. */
export function categoryOptions(rows: TransactionRow[]): { name: string; count: number; amount: number }[] {
  const byName = new Map<string, { name: string; count: number; amount: number }>();
  for (const t of rows) {
    for (const name of topCategories(t)) {
      const entry = byName.get(name) ?? { name, count: 0, amount: 0 };
      entry.count += 1;
      if (counts(t)) entry.amount += Math.abs(t.amount);
      byName.set(name, entry);
    }
  }
  return [...byName.values()].sort((a, b) => b.amount - a.amount || a.name.localeCompare(b.name));
}

/** Each account in the rows, with how many transactions it has. */
export function accountOptions(rows: TransactionRow[]): { id: string; label: string; institution: string; count: number }[] {
  const byId = new Map<string, { id: string; label: string; institution: string; count: number }>();
  for (const t of rows) {
    const entry = byId.get(t.account.id) ?? { id: t.account.id, label: accountLabel(t.account), institution: t.account.institution, count: 0 };
    entry.count += 1;
    byId.set(t.account.id, entry);
  }
  return [...byId.values()].sort((a, b) => b.count - a.count);
}
