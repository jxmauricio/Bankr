import { useEffect, type ReactNode } from "react";
import type { GoalProgress, SourceQuery, TransactionRow } from "../lib/api";
import { useCategories } from "../lib/useCategories";
import { RuleOffer } from "./RuleOffer";
import { TransactionEditor } from "./TransactionEditor";
import { formatMoney } from "../lib/format";
import { isTyping } from "../lib/useView";
import { accountLabel, merchantOf, signedAmount, topCategory } from "../lib/transactions";

/** A chat answer figure from this conversation, and the question that produced it. */
export interface Citation {
  question: string;
  footnote: number;
  query: SourceQuery;
}

function longDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric", year: "numeric" });
}

function shortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function initials(name: string): string {
  return name
    .replace(/[^A-Za-z ]/g, "")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase() || "·";
}

const KIND_LABEL: Record<string, string> = { income: "Income", expense: "Spending", transfer: "Transfer between your accounts" };

function citesThis(query: SourceQuery, t: TransactionRow): boolean {
  if (t.category_type !== "expense") return false;
  if (t.date < query.start || t.date > query.end) return false;
  if (query.category && query.category !== t.category && query.category !== t.parent_category) return false;
  if (query.merchant && !(t.merchant_name ?? "").toLowerCase().includes(query.merchant.toLowerCase())) return false;
  return true;
}

function goalFor(goals: GoalProgress[], t: TransactionRow): GoalProgress | undefined {
  if (t.category_type !== "expense") return undefined;
  return goals.find(
    (g) =>
      g.type === "track_spending" &&
      g.category &&
      (g.category === t.category || g.category === t.parent_category) &&
      (!g.window_start || t.date >= g.window_start) &&
      (!g.window_end || t.date <= g.window_end),
  );
}

/**
 * Everything Bankr knows about one transaction. A side drawer over the
 * Transactions table on desktop, full screen on phones. ↑ / ↓ step through
 * the rows currently shown; Esc closes.
 */
export function TransactionDetails({
  token,
  onUpdated,
  onRuleApplied,
  txn,
  position,
  count,
  all,
  goals,
  citations,
  onPrev,
  onNext,
  onClose,
  onSameMerchant,
  onAsk,
  onOpenAnswer,
}: {
  token: string;
  /** An edit saved; the row as the server now has it. */
  onUpdated: (row: Omit<TransactionRow, "account">) => void;
  /** A rule recategorized other rows; reload the list. */
  onRuleApplied: () => void;
  txn: TransactionRow;
  position: number;
  count: number;
  /** Every loaded row, for "here this period". */
  all: TransactionRow[];
  goals: GoalProgress[];
  citations: Citation[];
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
  onSameMerchant: (merchant: string) => void;
  onAsk: (question: string) => void;
  onOpenAnswer: () => void;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") return onClose();
      if (isTyping(e.target)) return;
      if (e.key === "ArrowUp") {
        e.preventDefault();
        onPrev();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        onNext();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onPrev, onNext, onClose]);
  const categories = useCategories(token);

  const merchant = merchantOf(txn);
  const amount = signedAmount(txn.amount);
  const kindColor = txn.category_type === "income" ? "text-signal" : txn.category_type === "transfer" ? "text-ink-soft" : "text-spend";
  const category = txn.is_split
    ? `Split ${txn.splits.length} ways`
    : txn.parent_category
      ? `${txn.category} · ${txn.parent_category}`
      : (txn.category ?? "Uncategorized");

  const visits = txn.merchant_name ? all.filter((t) => t.merchant_name === txn.merchant_name) : [txn];
  const visitMax = Math.max(...visits.map((v) => Math.abs(v.amount)), 1);
  const visitTotal = visits.reduce((s, v) => s + Math.abs(v.amount), 0);
  const visitMin = Math.min(...visits.map((v) => Math.abs(v.amount)));

  const goal = goalFor(goals, txn);
  const cited = citations.filter((c) => citesThis(c.query, txn));
  const short = merchant.split(" ·")[0];

  const fields: [string, string][] = [
    ["Status", txn.is_pending ? "Pending — amount may change" : "Posted"],
    ["Date", shortDate(txn.date)],
    ["Account", accountLabel(txn.account)],
    ["Bank", txn.account.institution],
    ["Category", category],
    ["Counts as", txn.is_excluded ? "Nothing — excluded from totals" : (KIND_LABEL[txn.category_type ?? ""] ?? "Not categorized")],
  ];

  const askText =
    txn.amount < 0
      ? `Tell me about the ${formatMoney(Math.abs(txn.amount))} at ${short} on ${shortDate(txn.date)}`
      : `Tell me about the ${formatMoney(txn.amount)} from ${short} on ${shortDate(txn.date)}`;

  return (
    <aside
      role="dialog"
      aria-label={`Transaction details: ${merchant}`}
      className="fixed inset-0 z-40 flex flex-col bg-bg lg:absolute lg:inset-y-0 lg:left-auto lg:right-0 lg:z-20 lg:w-[420px] lg:border-l lg:border-line-strong lg:shadow-[-24px_0_48px_rgb(0_0_0/0.45)]"
    >
      <div className="flex h-[60px] shrink-0 items-center justify-between border-b border-line pl-2 pr-3 lg:pl-5">
        <button
          type="button"
          onClick={onClose}
          className="flex h-11 cursor-pointer items-center gap-1.5 px-2 text-sm text-ink-soft hover:text-ink lg:hidden"
        >
          ‹ Transactions
        </button>
        <span className="hidden font-mono text-[11px] tracking-[0.1em] text-ink-faint lg:inline">
          TRANSACTION {position + 1} OF {count}
        </span>
        <div className="flex gap-1">
          <IconButton label="Previous transaction" onClick={onPrev} disabled={position === 0}>
            ↑
          </IconButton>
          <IconButton label="Next transaction" onClick={onNext} disabled={position >= count - 1}>
            ↓
          </IconButton>
          <span className="hidden lg:contents">
            <IconButton label="Close details" onClick={onClose}>
              ✕
            </IconButton>
          </span>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 lg:p-5">
        <div className="flex items-center gap-3.5">
          <span aria-hidden className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-[14px] bg-raised text-base font-semibold ${kindColor}`}>
            {initials(merchant)}
          </span>
          <div className="flex min-w-0 flex-col gap-1">
            <span className="truncate text-lg font-semibold text-ink">{merchant}</span>
            <span className="flex flex-wrap gap-1.5">
              <Chip>{topCategory(txn)}</Chip>
              {txn.is_pending ? <Chip className="bg-warn-soft text-warn">Pending</Chip> : <Chip>Posted</Chip>}
            </span>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <span className={`font-tabular text-[40px] font-medium leading-tight tracking-[-0.04em] ${amount.className}`}>{amount.text}</span>
          <span className="font-tabular text-xs text-ink-faint">{longDate(txn.date)}</span>
        </div>

        <dl className="m-0 rounded-[18px] bg-surface px-4 py-1">
          {fields.map(([k, v], i) => (
            <div key={k} className={`flex justify-between gap-4 py-[11px] ${i ? "border-t border-line" : ""}`}>
              <dt className="text-[13px] text-ink-soft">{k}</dt>
              <dd className="m-0 text-right font-tabular text-xs text-ink">{v}</dd>
            </div>
          ))}
        </dl>

        <TransactionEditor key={txn.id} token={token} txn={txn} categories={categories} onUpdated={onUpdated}>
          {(changedTo) =>
            changedTo && (
              <RuleOffer
                key={changedTo}
                token={token}
                txn={txn}
                categoryId={changedTo}
                categories={categories}
                onApplied={(n) => n > 0 && onRuleApplied()}
              />
            )
          }
        </TransactionEditor>

        {txn.merchant_name && (
          <section className="flex flex-col gap-2.5 rounded-[18px] bg-surface p-4">
            <div className="flex items-baseline justify-between gap-3">
              <span className="truncate text-[13px] font-semibold text-ink">{merchant} this period</span>
              <span className="shrink-0 font-tabular text-xs text-ink-soft">
                {visits.length} {visits.length === 1 ? "time" : "times"} · {formatMoney(visitTotal)}
              </span>
            </div>
            {visits.slice(0, 6).map((v) => {
              const isThis = v.id === txn.id;
              return (
                <div key={v.id} className={`flex items-center gap-2.5 text-xs ${isThis ? "text-ink" : "text-ink-soft"}`}>
                  <span className="w-12 font-tabular">{shortDate(v.date)}</span>
                  <span className="h-1.5 flex-1 rounded-full bg-line">
                    <span
                      className={`block h-1.5 rounded-full ${isThis ? (v.amount > 0 ? "bg-signal" : "bg-spend") : "bg-line-strong"}`}
                      style={{ width: `${Math.round((Math.abs(v.amount) / visitMax) * 100)}%` }}
                    />
                  </span>
                  <span className="w-[72px] text-right font-tabular">{formatMoney(Math.abs(v.amount))}</span>
                </div>
              );
            })}
            {visits.length > 6 && <span className="text-xs text-ink-faint">and {visits.length - 6} more</span>}
            <span className="text-xs text-ink-faint">
              {visits.length > 1 ? `Usually ${formatMoney(visitMin)}–${formatMoney(visitMax)} here.` : "The only time here in this period."}
            </span>
          </section>
        )}

        {goal && <GoalShare goal={goal} amount={Math.abs(txn.amount)} />}

        <section className="flex flex-col gap-2 rounded-[18px] bg-surface p-4">
          <span className="flex items-center gap-1.5 text-[13px] font-semibold text-ink">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-signal)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M12 3 5 6v5c0 4.4 3 8.3 7 9.5 4-1.2 7-5.1 7-9.5V6l-7-3Z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
            {cited.length ? `Used in ${cited.length} ${cited.length === 1 ? "answer" : "answers"}` : "Not used in any answer yet"}
          </span>
          {cited.map((c, i) => (
            <button
              key={i}
              type="button"
              onClick={onOpenAnswer}
              className="min-h-11 cursor-pointer rounded-xl bg-raised px-3 py-2 text-left text-[13px] text-ink-soft hover:text-ink"
            >
              “{c.question}” <span className="font-mono text-signal">{c.footnote}</span>
            </button>
          ))}
          <span className="text-xs text-ink-faint">
            {cited.length ? "Opens that answer in Chat." : "Answers in this conversation that rely on it will appear here."}
          </span>
        </section>
      </div>

      <div className="grid shrink-0 grid-cols-2 gap-2 border-t border-line px-4 pb-[max(20px,env(safe-area-inset-bottom))] pt-3.5 lg:px-5">
        {txn.merchant_name ? (
          <button
            type="button"
            onClick={() => onSameMerchant(txn.merchant_name!)}
            className="h-11 cursor-pointer truncate rounded-[14px] bg-raised px-3 text-[13px] text-ink hover:text-signal-hi"
          >
            All at {short}
          </button>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={() => onAsk(askText)}
          className="h-11 cursor-pointer rounded-[14px] bg-signal text-[13px] font-semibold text-bg hover:bg-signal-hi"
        >
          Ask Bankr about this
        </button>
      </div>
    </aside>
  );
}

/** The tracked category's progress, with this purchase as its own slice. */
function GoalShare({ goal, amount }: { goal: GoalProgress; amount: number }) {
  const target = goal.target_amount || 0;
  const spent = goal.current_progress_amount;
  const name = goal.name || goal.label || goal.category || "Spending tracker";
  const scale = Math.max(target, spent, 1);
  const spentPct = Math.min((spent / scale) * 100, 100);
  const slicePct = Math.min((amount / scale) * 100, spentPct);
  const over = goal.over_budget || (target > 0 && spent > target);
  const status = target > 0 ? (over ? `▲ ${formatMoney(spent - target)} over` : `${formatMoney(target - spent)} left`) : `${formatMoney(spent)} so far`;
  return (
    <section className="flex flex-col gap-2.5 rounded-[18px] bg-surface p-4">
      <div className="flex justify-between gap-3 text-[13px]">
        <span>
          <span className="text-ink-soft">Counts toward</span> <span className="font-semibold text-ink">{name}</span>
        </span>
        <span className={`font-tabular text-[11px] ${over ? "text-negative" : "text-ink-soft"}`}>{status}</span>
      </div>
      <div className="relative h-1.5 rounded-full bg-line">
        <div className={`absolute inset-y-0 left-0 rounded-l-full ${over ? "bg-negative" : "bg-ink-soft"}`} style={{ width: `${spentPct}%` }} />
        <div className="absolute inset-y-0 bg-ink" style={{ left: `${spentPct - slicePct}%`, width: `${slicePct}%` }} />
        {target > 0 && <div className="absolute -top-[5px] h-4 w-0.5 bg-ink" style={{ left: `${Math.min((target / scale) * 100, 100)}%` }} />}
      </div>
      <span className="text-xs text-ink-faint">The white slice is this purchase{target > 0 ? "; the tick is your limit" : ""}.</span>
    </section>
  );
}

function Chip({ children, className = "bg-raised text-ink-soft" }: { children: ReactNode; className?: string }) {
  return <span className={`rounded-full px-[9px] py-[3px] text-xs ${className}`}>{children}</span>;
}

function IconButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-xl bg-surface text-ink-soft hover:text-ink disabled:cursor-default disabled:opacity-40 lg:h-10 lg:w-10"
    >
      {children}
    </button>
  );
}
