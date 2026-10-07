import { useEffect, useMemo, useRef, useState } from "react";
import { fetchTransactions, type GoalProgress, type TransactionList, type TransactionRow } from "../lib/api";
import { formatMoney } from "../lib/format";
import { periodInfo, type Period } from "../lib/period";
import { isTyping } from "../lib/useView";
import { PeriodFilter } from "../components/PeriodFilter";
import { TransactionDetails, type Citation } from "../components/TransactionDetails";
import { accountLabel, merchantOf, signedAmount, topCategories, topCategory } from "../lib/transactions";

/** What Cash flow (or a details drawer) asks the list to show. */
export interface TransactionFilter {
  category: string | null;
  query: string;
}

function shortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function syncedAt(iso: string | null): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function TransactionsView({
  token,
  period,
  onPeriodChange,
  filter,
  onFilterChange,
  goals,
  citations,
  refreshKey,
  onAsk,
  onOpenChat,
  onEdited,
  focusId,
  onFocusHandled,
}: {
  token: string;
  period: Period;
  onPeriodChange: (period: Period) => void;
  filter: TransactionFilter;
  onFilterChange: (filter: TransactionFilter) => void;
  goals: GoalProgress[];
  citations: Citation[];
  refreshKey?: unknown;
  onAsk: (text: string) => void;
  onOpenChat: () => void;
  /** A row was edited -- totals elsewhere (goals, money rail) may have moved. */
  onEdited?: () => void;
  /** Open this transaction's details once it's loaded (e.g. from an insight). */
  focusId?: string | null;
  onFocusHandled?: () => void;
}) {
  const [list, setList] = useState<TransactionList | null>(null);
  const [failed, setFailed] = useState(false);
  const [account, setAccount] = useState<string>("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const window_ = periodInfo(period).window;

  // Only blank the list for a new period; a refresh after an edit swaps
  // rows in place so the open details drawer doesn't flicker shut.
  const loadedWindow = useRef<string | null>(null);
  useEffect(() => {
    let stale = false;
    setFailed(false);
    if (loadedWindow.current !== window_) setList(null);
    loadedWindow.current = window_;
    fetchTransactions(token, window_)
      .then((r) => !stale && setList(r))
      .catch(() => !stale && setFailed(true));
    return () => {
      stale = true;
    };
  }, [token, window_, refreshKey, reloads]);

  useEffect(() => {
    if (!focusId || !list) return;
    if (list.transactions.some((t) => t.id === focusId)) {
      onFilterChange({ category: null, query: "" });
      setSelectedId(focusId);
    }
    onFocusHandled?.();
  }, [focusId, list, onFilterChange, onFocusHandled]);

  // "/" jumps to search, like the hint in the box says.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "/" || isTyping(e.target) || document.querySelector('[aria-modal="true"]')) return;
      e.preventDefault();
      searchRef.current?.focus();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const all = useMemo(() => list?.transactions ?? [], [list]);
  const categories = useMemo(() => [...new Set(all.flatMap(topCategories))].sort(), [all]);
  const accounts = useMemo(() => {
    const seen = new Map<string, string>();
    for (const t of all) seen.set(t.account.id, accountLabel(t.account));
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [all]);

  const q = filter.query.trim().toLowerCase();
  const shown = all.filter(
    (t) =>
      (!filter.category || topCategories(t).includes(filter.category)) &&
      (!account || t.account.id === account) &&
      (!q ||
        merchantOf(t).toLowerCase().includes(q) ||
        (t.category ?? "").toLowerCase().includes(q) ||
        Math.abs(t.amount).toFixed(2).includes(q)),
  );
  const counts = (t: TransactionRow) => !t.is_excluded && t.category_type !== "transfer";
  const moneyIn = shown.reduce((s, t) => s + (t.amount > 0 && counts(t) ? t.amount : 0), 0);
  const moneyOut = shown.reduce((s, t) => s + (t.amount < 0 && counts(t) ? -t.amount : 0), 0);

  const position = shown.findIndex((t) => t.id === selectedId);
  const selected = position >= 0 ? shown[position] : null;
  const step = (delta: number) => {
    const next = shown[position + delta];
    if (next) setSelectedId(next.id);
  };

  const label = list?.label ?? periodInfo(period).label;
  const synced = syncedAt(list?.as_of ?? null);
  const hasFilter = Boolean(filter.category || filter.query || account);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col gap-3.5 px-4 pt-4 animate-view lg:px-8 lg:pt-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="m-0 text-[22px] font-semibold tracking-[-0.02em] text-ink lg:text-[26px]">Transactions</h1>
          <span className="font-tabular text-xs text-ink-faint">
            {label}
            {accounts.length > 0 && ` · ${accounts.length} account${accounts.length === 1 ? "" : "s"}`}
            {synced && ` · synced ${synced}`}
          </span>
        </div>
        <div className="flex gap-4 font-tabular text-[13px] lg:gap-5">
          <span className="text-ink-soft">{shown.length} shown</span>
          <span className="text-signal">In +{formatMoney(moneyIn)}</span>
          <span className="text-spend">Out −{formatMoney(moneyOut)}</span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex h-11 min-w-0 flex-[1_1_320px] items-center gap-2 rounded-[14px] border border-control bg-surface px-3.5 focus-within:border-signal">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-faint)" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
            <circle cx="11" cy="11" r="6" />
            <path d="m20 20-4.5-4.5" />
          </svg>
          <input
            ref={searchRef}
            value={filter.query}
            onChange={(e) => {
              onFilterChange({ ...filter, query: e.target.value });
              setSelectedId(null);
            }}
            placeholder="Search merchant, amount or category…"
            aria-label="Search transactions"
            aria-keyshortcuts="/"
            className="min-w-0 flex-1 bg-transparent text-base text-ink outline-none focus-visible:outline-none placeholder:text-ink-faint lg:text-sm"
          />
          <span aria-hidden className="hidden rounded-md border border-line-strong px-1.5 py-0.5 font-mono text-[10px] text-ink-faint lg:inline">
            /
          </span>
        </label>
        <div className="-mr-4 flex gap-2 overflow-x-auto pr-4 lg:mr-0 lg:pr-0">
          {filter.category && (
            <button
              type="button"
              onClick={() => onFilterChange({ ...filter, category: null })}
              aria-label={`Remove filter: ${filter.category}`}
              className="flex h-9 shrink-0 cursor-pointer items-center gap-2 rounded-full bg-spend/15 pl-3.5 pr-2.5 text-[13px] text-spend"
            >
              Category: {filter.category} <span aria-hidden>×</span>
            </button>
          )}
          <FilterSelect
            label="Category"
            value={filter.category ?? ""}
            onChange={(v) => onFilterChange({ ...filter, category: v || null })}
            options={categories.map((c) => [c, c])}
            showValue={false}
          />
          <FilterSelect label="Account" value={account} onChange={setAccount} options={accounts} />
          <div className="shrink-0 lg:hidden">
            <PeriodFilter period={period} onChange={onPeriodChange} />
          </div>
        </div>
      </div>

      <div className="mb-4 min-h-0 flex-1 overflow-y-auto rounded-[20px] bg-surface lg:mb-5">
        {failed ? (
          <EmptyState title="Couldn’t load transactions" body="Check your connection and switch views to try again." />
        ) : !list ? (
          <div className="flex flex-col gap-3 p-5" aria-label="Loading transactions">
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="h-4 animate-pulse rounded bg-raised" />
            ))}
          </div>
        ) : shown.length === 0 ? (
          <EmptyState
            title={`Nothing matches in ${label}`}
            body={hasFilter ? "Try a wider period or clear the filters." : "No transactions in this period yet."}
          />
        ) : (
          <>
            {/* Phones: two-line rows. */}
            <ul className="px-3.5 lg:hidden">
              {shown.map((t) => {
                const amt = signedAmount(t.amount);
                return (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(t.id)}
                      className="flex min-h-14 w-full cursor-pointer items-center justify-between gap-3 border-t border-line text-left first:border-t-0"
                    >
                      <span className="flex min-w-0 flex-col gap-0.5">
                        <span className="truncate text-sm text-ink">
                          {merchantOf(t)}
                          {t.is_pending && <span className="text-xs text-warn"> · pending</span>}
                          {t.is_excluded && <span className="text-xs text-ink-faint"> · excluded</span>}
                        </span>
                        <span className="font-tabular text-[11px] text-ink-faint">
                          {shortDate(t.date)} · {topCategory(t)}
                        </span>
                      </span>
                      <span className={`shrink-0 font-tabular text-sm ${amt.className}`}>{amt.text}</span>
                    </button>
                  </li>
                );
              })}
            </ul>

            {/* Desktop: a table. */}
            <table className="hidden w-full border-collapse text-sm lg:table">
              <thead className="sticky top-0 bg-surface">
                <tr className="text-left font-mono text-[11px] tracking-[0.08em] text-ink-faint">
                  <th scope="col" className="py-3 pl-5 pr-3 font-normal">DATE</th>
                  <th scope="col" className="p-3 font-normal">MERCHANT</th>
                  <th scope="col" className="p-3 font-normal">CATEGORY</th>
                  <th scope="col" className="p-3 font-normal">ACCOUNT</th>
                  <th scope="col" className="py-3 pl-3 pr-5 text-right font-normal">AMOUNT</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((t) => {
                  const amt = signedAmount(t.amount);
                  const isSelected = t.id === selectedId;
                  return (
                    <tr
                      key={t.id}
                      onClick={() => setSelectedId(isSelected ? null : t.id)}
                      aria-selected={isSelected}
                      className={`cursor-pointer border-t border-line hover:bg-raised ${isSelected ? "bg-raised" : ""} ${t.is_excluded ? "opacity-55" : ""}`}
                    >
                      <td className="py-[11px] pl-5 pr-3 font-tabular text-xs text-ink-soft">{shortDate(t.date)}</td>
                      <td className="max-w-[280px] truncate px-3 py-[11px] text-ink">
                        {/* The row is the click target; this button makes it reachable by keyboard. */}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedId(isSelected ? null : t.id);
                          }}
                          className="cursor-pointer text-left"
                        >
                          {merchantOf(t)}
                        </button>
                        {t.is_pending && <span className="text-xs text-warn"> · pending</span>}
                        {t.is_excluded && <span className="text-xs text-ink-faint"> · excluded</span>}
                      </td>
                      <td className="px-3 py-[11px]">
                        <span className="rounded-full bg-raised px-[9px] py-[3px] text-xs text-ink-soft">{topCategory(t)}</span>
                      </td>
                      <td className="px-3 py-[11px] font-tabular text-xs text-ink-soft">{accountLabel(t.account)}</td>
                      <td className={`py-[11px] pl-3 pr-5 text-right font-tabular ${amt.className}`}>{amt.text}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {list.truncated && (
              <p className="px-5 py-3 text-center text-xs text-ink-faint">
                Showing the newest {all.length} of {list.transaction_count}. Pick a shorter period to see the rest.
              </p>
            )}
          </>
        )}
      </div>

      {selected && (
        <TransactionDetails
          token={token}
          onUpdated={(row) => {
            setList((l) => l && { ...l, transactions: l.transactions.map((t) => (t.id === row.id ? { ...t, ...row } : t)) });
            onEdited?.();
          }}
          onRuleApplied={() => {
            setReloads((n) => n + 1);
            onEdited?.();
          }}
          txn={selected}
          position={position}
          count={shown.length}
          all={all}
          goals={goals}
          citations={citations}
          onPrev={() => step(-1)}
          onNext={() => step(1)}
          onClose={() => setSelectedId(null)}
          onSameMerchant={(merchant) => {
            onFilterChange({ category: null, query: merchant });
            setSelectedId(null);
          }}
          onAsk={onAsk}
          onOpenAnswer={onOpenChat}
        />
      )}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  showValue = true,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
  /** False when a removable chip already names the choice. */
  showValue?: boolean;
}) {
  const active = showValue && value !== "";
  return (
    <label
      className={`relative flex h-9 shrink-0 items-center rounded-full border px-3 text-[13px] focus-within:border-signal ${
        active ? "border-line-strong bg-raised text-ink" : "border-dashed border-line-strong text-ink-soft"
      }`}
    >
      <span className="pointer-events-none whitespace-nowrap">
        {active ? options.find(([v]) => v === value)?.[1] ?? label : label} ▾
      </span>
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="absolute inset-0 cursor-pointer opacity-0"
      >
        <option value="">{label === "Category" ? "All categories" : "All accounts"}</option>
        {options.map(([v, text]) => (
          <option key={v} value={v}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center gap-2 px-5 py-10 text-center">
      <span className="text-[15px] text-ink">{title}</span>
      <span className="text-[13px] text-ink-soft">{body}</span>
    </div>
  );
}
