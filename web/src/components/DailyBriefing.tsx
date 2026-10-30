import { useEffect, useState } from "react";
import {
  ApiError,
  fetchBriefingHelp,
  fetchTodayBriefing,
  markBriefingRead,
  runBriefingAction,
  type BriefingAction,
  type BriefingHelp,
  type BriefingItem,
  type DailyBriefing,
} from "../lib/api";
import { useCategories } from "../lib/useCategories";
import { CategorySelect } from "./CategorySelect";

const TYPE_LABEL: Record<BriefingItem["type"], string> = {
  review: "Needs a category",
  unusual: "Unusual charge",
  duplicate: "Possible duplicate",
  price_change: "Price change",
  renewal: "Renews soon",
  trial: "Possible trial",
};

const ACTION_LABEL: Record<BriefingAction, string> = {
  recategorize: "Recategorize",
  create_rule: "Make a rule",
  mark_expected: "It's expected",
  dismiss: "Dismiss",
};

const STATUS_LABEL: Record<Exclude<BriefingItem["status"], "open">, string> = {
  done: "Fixed",
  expected: "Marked expected",
  dismissed: "Dismissed",
};

/** Money rail card: today's briefing at a glance. Opens the full list. */
export function DailyBriefingCard({
  token,
  refreshKey,
  version,
  onOpen,
}: {
  token: string;
  refreshKey?: unknown;
  /** Bump to refetch after a fix made in the briefing. */
  version?: number;
  onOpen: () => void;
}) {
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null);

  useEffect(() => {
    let stale = false;
    fetchTodayBriefing(token)
      .then((b) => !stale && setBriefing(b))
      .catch(() => {});
    return () => {
      stale = true;
    };
  }, [token, refreshKey, version]);

  if (!briefing || !briefing.items.length) return null;
  const done = briefing.open_count === 0;
  return (
    <button type="button" onClick={onOpen} className="flex w-full cursor-pointer flex-col gap-1 card p-4 text-left hover:bg-raised">
      <span className="flex items-center gap-2 font-mono text-[11px] tracking-[0.12em] text-ink-faint">
        TODAY'S BRIEFING
        {!done && (
          <span className="rounded-full bg-signal-wash px-1.5 py-px font-tabular text-[10px] font-semibold text-signal">
            {briefing.open_count}
          </span>
        )}
      </span>
      <span className={`text-sm ${done ? "text-ink-soft" : "text-ink"}`}>
        {done ? "All handled. Nice." : (briefing.intro ?? briefing.teaser)}
      </span>
      {!done && <span className="text-xs text-signal">Review {briefing.open_count === 1 ? "it" : "them"} →</span>}
    </button>
  );
}

/** Every item in today's briefing, each with its one-tap fixes behind a confirm step. */
export function DailyBriefingModal({
  token,
  onClose,
  onChanged,
}: {
  token: string;
  onClose: () => void;
  /** A fix changed transactions or rules; the rest of the app should reload. */
  onChanged: () => void;
}) {
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTodayBriefing(token)
      .then((b) => {
        setBriefing(b);
        if (!b.read) markBriefingRead(token).catch(() => {});
      })
      .catch(() => setError("Couldn't load today's briefing. Try again."));
  }, [token]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const open = briefing?.items.filter((i) => i.status === "open") ?? [];
  const handled = briefing?.items.filter((i) => i.status !== "open") ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-scrim px-4" onClick={onClose} role="presentation">
      <div
        className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-3xl border border-line-strong bg-surface shadow-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="briefing-title"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 id="briefing-title" className="font-display text-lg font-semibold text-ink">
              Today's briefing
            </h2>
            {briefing && (
              <p className="mt-0.5 text-[13px] text-ink-soft">
                {briefing.open_count === 0 ? "Everything's handled for today." : (briefing.intro ?? briefing.teaser)}
              </p>
            )}
          </div>
          <button type="button" onClick={onClose} className="shrink-0 cursor-pointer text-sm text-ink-soft hover:text-ink">
            Close
          </button>
        </div>

        <div className="overflow-y-auto px-5 py-4">
          {error && (
            <p role="alert" className="text-sm text-negative">
              {error}
            </p>
          )}
          {!briefing && !error && <p className="text-sm text-ink-faint">Loading…</p>}
          {briefing && briefing.items.length === 0 && (
            <p className="py-6 text-center text-sm text-ink-soft">Nothing needs you today.</p>
          )}
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {open.map((item) => (
              <BriefingRow
                key={item.key}
                token={token}
                item={item}
                onUpdated={(b) => {
                  setBriefing(b);
                  onChanged();
                }}
              />
            ))}
          </ul>
          {handled.length > 0 && (
            <>
              <h3 className="mb-2 mt-5 font-mono text-[11px] tracking-[0.12em] text-ink-faint">HANDLED</h3>
              <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                {handled.map((item) => (
                  <li key={item.key} className="flex items-center justify-between gap-3 text-[13px]">
                    <span className="min-w-0 truncate text-ink-soft line-through decoration-ink-faint">{item.title}</span>
                    <span className="shrink-0 text-xs text-ink-faint">{STATUS_LABEL[item.status as keyof typeof STATUS_LABEL]}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="mt-5 text-xs text-ink-faint">
            Bankr never cancels, contacts a merchant or sends an email for you. Every change here waits for your confirm.
          </p>
        </div>
      </div>
    </div>
  );
}

type Pending = { action: BriefingAction; summary: string; categoryId?: string };

function BriefingRow({
  token,
  item,
  onUpdated,
}: {
  token: string;
  item: BriefingItem;
  onUpdated: (briefing: DailyBriefing) => void;
}) {
  const categories = useCategories(token);
  const needsCategory = item.actions.includes("recategorize");
  const [categoryId, setCategoryId] = useState(item.suggestion?.category_id ?? "");
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [help, setHelp] = useState<BriefingHelp | "loading" | null>(null);

  async function preview(action: BriefingAction) {
    setError(null);
    setBusy(true);
    const category = action === "recategorize" || action === "create_rule" ? categoryId : undefined;
    try {
      const r = await runBriefingAction(token, { item_key: item.key, action, category_id: category || undefined, confirm: false });
      setPending({ action, summary: r.summary, categoryId: category });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't do that. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      const r = await runBriefingAction(token, {
        item_key: item.key,
        action: pending.action,
        category_id: pending.categoryId || undefined,
        confirm: true,
      });
      if (r.briefing) onUpdated(r.briefing);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't do that. Try again.");
      setBusy(false);
    }
  }

  async function loadHelp() {
    if (help) return setHelp(null);
    setHelp("loading");
    try {
      setHelp(await fetchBriefingHelp(token, item.key));
    } catch {
      setHelp(null);
      setError("Couldn't load help for this one.");
    }
  }

  return (
    <li className="rounded-[16px] border border-line p-3.5">
      <span className="font-mono text-[10px] tracking-[0.1em] text-ink-faint">{TYPE_LABEL[item.type].toUpperCase()}</span>
      <p className="m-0 mt-0.5 text-sm font-medium text-ink">{item.title}</p>
      <p className="m-0 mt-0.5 text-[13px] text-ink-soft">{item.detail}</p>

      {pending ? (
        <div className="mt-3 rounded-xl bg-raised p-3">
          <p className="m-0 text-[13px] text-ink">{pending.summary}</p>
          <div className="mt-2.5 flex gap-2">
            <button
              type="button"
              onClick={confirm}
              disabled={busy}
              className="h-9 cursor-pointer rounded-lg bg-signal px-3 text-[13px] font-semibold text-on-signal disabled:opacity-60"
            >
              {busy ? "Working…" : "Confirm"}
            </button>
            <button
              type="button"
              onClick={() => setPending(null)}
              disabled={busy}
              className="h-9 cursor-pointer rounded-lg px-3 text-[13px] text-ink-soft hover:text-ink disabled:opacity-60"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          {needsCategory && (
            <CategorySelect
              categories={categories}
              value={categoryId}
              onChange={setCategoryId}
              label={`Category for ${item.merchant ?? "this merchant"}`}
              className="mt-3 w-full"
            />
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {item.actions.map((action) => (
              <button
                key={action}
                type="button"
                onClick={() => preview(action)}
                disabled={busy || ((action === "recategorize" || action === "create_rule") && !categoryId)}
                className={`h-9 cursor-pointer rounded-lg px-3 text-[13px] disabled:cursor-default disabled:opacity-50 ${
                  action === item.actions[0] ? "bg-ink font-semibold text-bg" : "border border-line text-ink hover:bg-raised"
                }`}
              >
                {ACTION_LABEL[action]}
              </button>
            ))}
            {item.has_help && (
              <button
                type="button"
                onClick={loadHelp}
                aria-expanded={help !== null}
                className="h-9 cursor-pointer rounded-lg px-2 text-[13px] text-signal hover:text-signal-hi"
              >
                {item.type === "unusual" || item.type === "duplicate" ? "Ask for a refund" : "How to cancel"}
              </button>
            )}
          </div>
        </>
      )}

      {error && (
        <p role="alert" className="m-0 mt-2 text-[13px] text-negative">
          {error}
        </p>
      )}
      {help === "loading" && <p className="m-0 mt-3 text-[13px] text-ink-faint">Looking it up…</p>}
      {help && help !== "loading" && <HelpPanel help={help} />}
    </li>
  );
}

function HelpPanel({ help }: { help: BriefingHelp }) {
  const [copied, setCopied] = useState<string | null>(null);

  function copy(subject: string, body: string) {
    navigator.clipboard
      .writeText(`Subject: ${subject}\n\n${body}`)
      .then(() => {
        setCopied(subject);
        setTimeout(() => setCopied(null), 2000);
      })
      .catch(() => {});
  }

  return (
    <div className="mt-3 flex flex-col gap-3 rounded-xl bg-raised p-3">
      {help.cancel ? (
        <a href={help.cancel.url} target="_blank" rel="noreferrer noopener" className="text-[13px] text-signal underline hover:text-signal-hi">
          {help.cancel.title} ↗
          {help.cancel.source === "search" && <span className="ml-1 text-ink-faint no-underline">(from a web search)</span>}
        </a>
      ) : (
        help.emails.some((e) => e.kind === "cancellation") && (
          <p className="m-0 text-[13px] text-ink-soft">No cancel page on file for {help.merchant}. The email below works for most.</p>
        )
      )}
      {help.emails.map((email) => (
        <div key={email.subject} className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[13px] font-medium text-ink">{email.subject}</span>
            <button
              type="button"
              onClick={() => copy(email.subject, email.body)}
              className="shrink-0 cursor-pointer text-xs text-signal hover:text-signal-hi"
            >
              {copied === email.subject ? "Copied" : "Copy"}
            </button>
          </div>
          <pre className="m-0 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-surface p-2.5 font-sans text-[12px] text-ink-soft">
            {email.body}
          </pre>
        </div>
      ))}
      <p className="m-0 text-[11px] text-ink-faint">Copy it into your own email. Bankr doesn't send anything.</p>
    </div>
  );
}
