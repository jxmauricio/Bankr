import { useEffect, useState, type ReactNode } from "react";
import {
  ApiError,
  deleteBudget,
  fetchBudget,
  fetchBudgetSuggestion,
  moveBudgetMoney,
  setupBudget,
  updateBudgetSettings,
  upsertBudget,
  type BudgetLine,
  type BudgetStatus,
} from "../lib/api";
import { formatMoney } from "../lib/format";
import { useCategories } from "../lib/useCategories";

const whole = (n: number) => `${n < 0 ? "−" : ""}$${Math.abs(Math.round(n)).toLocaleString("en-US")}`;

function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * This month's budget: what's left in each line, with rollover and
 * "cover overspending" moves. Flex mode shows fixed bills plus one
 * Flexible bucket; category mode shows a line per category.
 */
export function BudgetSection({
  token,
  refreshKey,
  focus,
  onChanged,
}: {
  token: string;
  refreshKey?: unknown;
  focus?: boolean;
  /** A budget change that other surfaces might show. */
  onChanged?: () => void;
}) {
  const categories = useCategories(token);
  const [month, setMonth] = useState<string | null>(null);
  const [status, setStatus] = useState<BudgetStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [covering, setCovering] = useState<BudgetLine | null>(null);

  useEffect(() => {
    let stale = false;
    fetchBudget(token, month ?? undefined)
      .then((s) => {
        if (stale) return;
        setStatus(s);
        setFailed(false);
      })
      .catch(() => !stale && setFailed(true));
    return () => {
      stale = true;
    };
  }, [token, month, refreshKey]);

  async function run(action: () => Promise<BudgetStatus>) {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      // Edits answer with the current month; refetch if another is open.
      setStatus(month && next.month !== month ? await fetchBudget(token, month) : next);
      onChanged?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (failed) return <Shell focus={focus}><p className="py-6 text-center text-sm text-ink-soft">Couldn’t load your budget.</p></Shell>;
  if (!status) return <div className="h-[320px] animate-pulse rounded-3xl bg-surface" aria-label="Loading budget" />;

  const isCurrent = status.month === status.today.slice(0, 7);
  const allLines = [...status.lines, ...(status.flex ? [status.flex] : [])];
  const budgetedIds = new Set(status.lines.map((l) => l.category_id));
  const addable = categories.filter((c) => c.type === "expense" && !budgetedIds.has(c.id));

  if (!status.has_budget) {
    return (
      <Shell focus={focus}>
        <Header status={status} onMonth={setMonth} />
        <div className="flex flex-col items-start gap-3 rounded-[18px] bg-raised p-5">
          <p className="m-0 text-[15px] font-semibold text-ink">Set a budget for the month</p>
          <p className="m-0 max-w-[520px] text-[13px] text-ink-soft">
            Bankr can start you from what you actually spent over the last three months: fixed bills like rent get their own
            line, and everything else shares one flexible amount. You can change any of it after.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const s = await fetchBudgetSuggestion(token);
                return setupBudget(token, { mode: "flex", flex_amount: s.flex_amount, lines: s.lines });
              })
            }
            className="h-11 cursor-pointer rounded-[14px] bg-signal px-4 text-sm font-semibold text-bg hover:bg-signal-hi disabled:opacity-60"
          >
            {busy ? "Setting up…" : "Start from my last 3 months"}
          </button>
          {error && <p className="m-0 text-xs text-negative">{error}</p>}
        </div>
      </Shell>
    );
  }

  return (
    <Shell focus={focus}>
      <Header status={status} onMonth={setMonth}>
        <div role="radiogroup" aria-label="Budget style" className="flex rounded-[12px] bg-raised p-[3px]">
          {(["flex", "category"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={status.mode === mode}
              disabled={busy}
              onClick={() => status.mode !== mode && run(() => updateBudgetSettings(token, { mode }))}
              className={`h-8 cursor-pointer rounded-[9px] px-3 text-xs ${status.mode === mode ? "bg-surface text-ink" : "text-ink-soft hover:text-ink"}`}
            >
              {mode === "flex" ? "Flexible" : "By category"}
            </button>
          ))}
        </div>
      </Header>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Income so far" value={whole(status.income.so_far)} hint={`${whole(status.income.last_month)} last month`} />
        <Stat label="Budgeted" value={whole(status.totals.budgeted)} />
        <Stat label="Spent" value={whole(status.totals.spent)} />
        <Stat
          label={status.totals.available < 0 ? "Over" : "Left to spend"}
          value={whole(Math.abs(status.totals.available))}
          tone={status.totals.available < 0 ? "text-negative" : "text-signal"}
        />
      </div>

      {status.mode === "flex" && status.flex && (
        <FlexCard
          line={status.flex}
          busy={busy}
          isCurrent={isCurrent}
          onAmount={(amount) => run(() => updateBudgetSettings(token, { flex_amount: amount }))}
          onRollover={(on) => run(() => updateBudgetSettings(token, { flex_rollover: on }))}
          onCover={() => setCovering(status.flex)}
        />
      )}

      <div className="flex flex-col">
        {status.lines.length > 0 && (
          <span className="pb-1 text-[13px] font-semibold text-ink">{status.mode === "flex" ? "Fixed" : "Categories"}</span>
        )}
        {status.lines.map((line) => (
          <LineRow
            key={line.key}
            line={line}
            busy={busy}
            isCurrent={isCurrent}
            onAmount={(amount) => run(() => upsertBudget(token, line.category_id!, { amount }))}
            onRollover={(on) => run(() => upsertBudget(token, line.category_id!, { rollover: on }))}
            onRemove={() => run(() => deleteBudget(token, line.category_id!))}
            onCover={() => setCovering(line)}
          />
        ))}
        {status.mode === "category" && status.unbudgeted.length > 0 && (
          <div className="mt-3 flex flex-col gap-1.5 rounded-[14px] bg-raised p-3">
            <span className="text-xs text-ink-soft">Spent without a budget</span>
            {status.unbudgeted.map((u) => (
              <div key={u.category_id} className="flex items-center justify-between gap-3 text-[13px]">
                <span className="text-ink">{u.name}</span>
                <span className="flex items-center gap-3">
                  <span className="font-tabular text-ink-soft">{formatMoney(u.spent)}</span>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => run(() => upsertBudget(token, u.category_id, { amount: Math.ceil(u.spent / 10) * 10 }))}
                    className="h-8 cursor-pointer rounded-lg px-2 text-xs text-signal hover:text-signal-hi"
                  >
                    Budget it
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}
        <AddLine
          options={addable}
          busy={busy}
          label={status.mode === "flex" ? "Add a fixed bill" : "Add a category"}
          onAdd={(categoryId, amount) =>
            run(() => upsertBudget(token, categoryId, { amount, group: status.mode === "flex" ? "fixed" : undefined }))
          }
        />
      </div>

      {error && <p className="m-0 text-xs text-negative">{error}</p>}

      {covering && (
        <CoverDialog
          target={covering}
          lines={allLines}
          onClose={() => setCovering(null)}
          onMove={async (fromKey, amount) => {
            await run(() => moveBudgetMoney(token, { month: status.month, from_key: fromKey, to_key: covering.key, amount }));
            setCovering(null);
          }}
        />
      )}
    </Shell>
  );
}

function Shell({ children, focus }: { children: ReactNode; focus?: boolean }) {
  return (
    <section
      id="budget"
      ref={(el) => {
        if (focus && el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      }}
      className={`relative flex flex-col gap-4 rounded-3xl bg-surface p-4 md:px-7 md:py-6 ${focus ? "ring-1 ring-signal/40" : ""}`}
    >
      {children}
    </section>
  );
}

function Header({ status, onMonth, children }: { status: BudgetStatus; onMonth: (m: string) => void; children?: ReactNode }) {
  const isCurrent = status.month === status.today.slice(0, 7);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <h2 className="m-0 text-lg font-semibold text-ink">Budget</h2>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            aria-label="Previous month"
            onClick={() => onMonth(shiftMonth(status.month, -1))}
            className="h-9 w-9 cursor-pointer rounded-lg text-ink-soft hover:text-ink"
          >
            ‹
          </button>
          <span className="min-w-[124px] text-center text-[13px] text-ink">{status.label}</span>
          <button
            type="button"
            aria-label="Next month"
            disabled={isCurrent}
            onClick={() => onMonth(shiftMonth(status.month, 1))}
            className="h-9 w-9 cursor-pointer rounded-lg text-ink-soft hover:text-ink disabled:cursor-default disabled:opacity-30"
          >
            ›
          </button>
        </div>
      </div>
      {children}
    </div>
  );
}

function Stat({ label, value, hint, tone = "text-ink" }: { label: string; value: string; hint?: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-[14px] bg-raised px-3.5 py-3">
      <span className="text-[11px] text-ink-faint">{label}</span>
      <span className={`font-tabular text-lg font-medium ${tone}`}>{value}</span>
      {hint && <span className="font-tabular text-[11px] text-ink-faint">{hint}</span>}
    </div>
  );
}

function Bar({ line }: { line: BudgetLine }) {
  const room = Math.max(line.budgeted + line.carryover + line.moved, 0);
  const scale = Math.max(room, line.spent, 1);
  const color = line.status === "over" ? "bg-negative" : line.status === "warning" ? "bg-warn" : "bg-signal";
  return (
    <div className="relative h-1.5 rounded-full bg-line">
      <div className={`absolute inset-y-0 left-0 rounded-full ${color}`} style={{ width: `${Math.min((line.spent / scale) * 100, 100)}%` }} />
      {line.spent > room && room > 0 && (
        <div className="absolute -top-[4px] h-3.5 w-0.5 bg-ink" style={{ left: `${(room / scale) * 100}%` }} />
      )}
    </div>
  );
}

function leftText(line: BudgetLine): { text: string; tone: string } {
  if (line.available < 0) return { text: `${formatMoney(-line.available)} over`, tone: "text-negative" };
  return { text: `${formatMoney(line.available)} left`, tone: line.status === "warning" ? "text-warn" : "text-ink" };
}

function detail(line: BudgetLine, isCurrent: boolean): string {
  const parts = [`${formatMoney(line.spent)} of ${formatMoney(line.budgeted)}`];
  if (line.carryover) parts.push(`${line.carryover > 0 ? "+" : "−"}${formatMoney(Math.abs(line.carryover))} rolled over`);
  if (line.moved) parts.push(`${line.moved > 0 ? "+" : "−"}${formatMoney(Math.abs(line.moved))} moved`);
  if (isCurrent && line.status === "warning" && line.projected_spent != null) {
    parts.push(`on pace for ${formatMoney(line.projected_spent)}`);
  }
  return parts.join(" · ");
}

function FlexCard({
  line,
  busy,
  isCurrent,
  onAmount,
  onRollover,
  onCover,
}: {
  line: NonNullable<BudgetStatus["flex"]>;
  busy: boolean;
  isCurrent: boolean;
  onAmount: (amount: number) => void;
  onRollover: (on: boolean) => void;
  onCover: () => void;
}) {
  const left = leftText(line);
  return (
    <div className="flex flex-col gap-2.5 rounded-[18px] bg-raised p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="flex items-baseline gap-2">
          <span className="text-[15px] font-semibold text-ink">Flexible</span>
          <AmountField value={line.budgeted} disabled={busy} label="Flexible budget" onCommit={onAmount} />
        </span>
        <span className={`font-tabular text-[15px] font-medium ${left.tone}`}>{left.text}</span>
      </div>
      <Bar line={line} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-tabular text-xs text-ink-soft">{detail(line, isCurrent)}</span>
        <LineActions line={line} busy={busy} onRollover={onRollover} onCover={onCover} />
      </div>
      {line.categories.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {line.categories.map((c) => (
            <span key={c.category_id} className="rounded-full bg-surface px-2.5 py-1 text-xs text-ink-soft">
              {c.name} <span className="font-tabular text-ink">{formatMoney(c.spent)}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function LineRow({
  line,
  busy,
  isCurrent,
  onAmount,
  onRollover,
  onRemove,
  onCover,
}: {
  line: BudgetLine;
  busy: boolean;
  isCurrent: boolean;
  onAmount: (amount: number) => void;
  onRollover: (on: boolean) => void;
  onRemove: () => void;
  onCover: () => void;
}) {
  const left = leftText(line);
  return (
    <div className="flex flex-col gap-2 border-t border-line py-3 first-of-type:border-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="truncate text-[13px] text-ink">{line.name}</span>
          <AmountField value={line.budgeted} disabled={busy} label={`${line.name} budget`} onCommit={onAmount} />
        </span>
        <span className={`shrink-0 font-tabular text-[13px] ${left.tone}`}>{left.text}</span>
      </div>
      <Bar line={line} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-tabular text-[11px] text-ink-faint">{detail(line, isCurrent)}</span>
        <span className="flex items-center gap-1">
          <LineActions line={line} busy={busy} onRollover={onRollover} onCover={onCover} />
          <button
            type="button"
            aria-label={`Remove ${line.name} budget`}
            disabled={busy}
            onClick={onRemove}
            className="h-8 cursor-pointer rounded-lg px-2 text-xs text-ink-faint hover:text-negative"
          >
            Remove
          </button>
        </span>
      </div>
    </div>
  );
}

function LineActions({
  line,
  busy,
  onRollover,
  onCover,
}: {
  line: BudgetLine;
  busy: boolean;
  onRollover: (on: boolean) => void;
  onCover: () => void;
}) {
  return (
    <span className="flex items-center gap-1">
      {line.available < 0 && (
        <button
          type="button"
          disabled={busy}
          onClick={onCover}
          className="h-8 cursor-pointer rounded-lg bg-negative-soft px-2.5 text-xs font-medium text-negative hover:brightness-125"
        >
          Cover it
        </button>
      )}
      <button
        type="button"
        aria-pressed={line.rollover}
        disabled={busy}
        onClick={() => onRollover(!line.rollover)}
        title="Carry what's left (or overspent) into next month"
        className={`h-8 cursor-pointer rounded-lg px-2 text-xs ${line.rollover ? "text-signal" : "text-ink-faint hover:text-ink"}`}
      >
        ↻ Rollover {line.rollover ? "on" : "off"}
      </button>
    </span>
  );
}

/** A dollar amount that turns into an input on click. */
function AmountField({ value, label, disabled, onCommit }: { value: number; label: string; disabled?: boolean; onCommit: (n: number) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  if (!editing) {
    return (
      <button
        type="button"
        aria-label={`Edit ${label}`}
        disabled={disabled}
        onClick={() => {
          setDraft(String(value));
          setEditing(true);
        }}
        className="cursor-pointer rounded-md px-1 font-tabular text-xs text-ink-faint underline decoration-dotted underline-offset-4 hover:text-ink"
      >
        {formatMoney(value)}
      </button>
    );
  }
  const commit = () => {
    setEditing(false);
    const n = Math.round(parseFloat(draft) * 100) / 100;
    if (Number.isFinite(n) && n >= 0 && n !== value) onCommit(n);
  };
  return (
    <input
      autoFocus
      onFocus={(e) => e.currentTarget.select()}
      aria-label={label}
      inputMode="decimal"
      value={draft}
      onChange={(e) => setDraft(e.target.value.replace(/[^0-9.]/g, ""))}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") setEditing(false);
      }}
      className="h-7 w-[88px] rounded-md border border-signal bg-surface px-1.5 font-tabular text-xs text-ink outline-none"
    />
  );
}

function AddLine({
  options,
  busy,
  label,
  onAdd,
}: {
  options: { id: string; name: string }[];
  busy: boolean;
  label: string;
  onAdd: (categoryId: string, amount: number) => void;
}) {
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  if (!options.length) return null;
  const n = parseFloat(amount);
  return (
    <form
      className="mt-2 flex flex-wrap items-center gap-2 border-t border-line pt-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!categoryId || !(n >= 0)) return;
        onAdd(categoryId, n);
        setCategoryId("");
        setAmount("");
      }}
    >
      <select
        aria-label={label}
        value={categoryId}
        onChange={(e) => setCategoryId(e.target.value)}
        className="h-9 min-w-0 flex-1 cursor-pointer rounded-lg border border-line bg-raised px-2 text-xs text-ink"
      >
        <option value="">{label}…</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
      <label className="flex h-9 w-[110px] items-center gap-1 rounded-lg border border-line bg-raised px-2 focus-within:border-signal">
        <span className="text-xs text-ink-faint">$</span>
        <input
          aria-label="Monthly amount"
          inputMode="decimal"
          placeholder="per month"
          value={amount}
          onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ""))}
          className="w-full min-w-0 bg-transparent font-tabular text-xs text-ink outline-none placeholder:text-ink-faint"
        />
      </label>
      <button
        type="submit"
        disabled={busy || !categoryId || !(n >= 0)}
        className="h-9 cursor-pointer rounded-lg bg-raised px-3 text-xs text-ink hover:text-signal-hi disabled:cursor-default disabled:opacity-40"
      >
        Add
      </button>
    </form>
  );
}

function CoverDialog({
  target,
  lines,
  onClose,
  onMove,
}: {
  target: BudgetLine;
  lines: BudgetLine[];
  onClose: () => void;
  onMove: (fromKey: string, amount: number) => Promise<void>;
}) {
  const sources = lines.filter((l) => l.key !== target.key && l.available > 0).sort((a, b) => b.available - a.available);
  const need = Math.round(-target.available * 100) / 100;
  const [fromKey, setFromKey] = useState(sources[0]?.key ?? "");
  const [amount, setAmount] = useState(() => String(Math.min(need, sources[0]?.available ?? need)));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const n = parseFloat(amount);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 px-4" onClick={() => !busy && onClose()} role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="cover-title"
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-sm flex-col gap-4 rounded-3xl border border-line-strong bg-surface p-6 shadow-modal"
      >
        <div>
          <h3 id="cover-title" className="m-0 text-base font-semibold text-ink">
            Cover {target.name}
          </h3>
          <p className="m-0 mt-1 text-[13px] text-ink-soft">
            It's {formatMoney(need)} over. Move money from a line that has room.
          </p>
        </div>
        {sources.length === 0 ? (
          <p className="m-0 text-[13px] text-ink-soft">No other line has money left this month. Raise this line's amount instead.</p>
        ) : (
          <>
            <label className="flex flex-col gap-1 text-xs text-ink-soft">
              From
              <select
                value={fromKey}
                onChange={(e) => setFromKey(e.target.value)}
                className="h-10 cursor-pointer rounded-xl border border-line bg-raised px-2.5 text-[13px] text-ink"
              >
                {sources.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.name} — {formatMoney(s.available)} left
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-soft">
              Amount
              <span className="flex h-10 items-center gap-1 rounded-xl border border-line bg-raised px-2.5 focus-within:border-signal">
                <span className="text-[13px] text-ink-faint">$</span>
                <input
                  inputMode="decimal"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ""))}
                  className="w-full bg-transparent font-tabular text-[13px] text-ink outline-none"
                />
              </span>
            </label>
          </>
        )}
        <div className="grid grid-cols-2 gap-2">
          <button type="button" disabled={busy} onClick={onClose} className="h-11 cursor-pointer rounded-[14px] bg-raised text-sm text-ink">
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || !fromKey || !(n > 0)}
            onClick={async () => {
              setBusy(true);
              try {
                await onMove(fromKey, n);
              } finally {
                setBusy(false);
              }
            }}
            className="h-11 cursor-pointer rounded-[14px] bg-signal text-sm font-semibold text-bg hover:bg-signal-hi disabled:cursor-default disabled:opacity-40"
          >
            {busy ? "Moving…" : "Move"}
          </button>
        </div>
      </div>
    </div>
  );
}
