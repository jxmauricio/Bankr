import { useEffect, useRef, useState } from "react";
import { ApiError, confirmProposal, dismissProposal, fetchProposals, type McpProposal } from "../lib/api";
import { formatRelativeTime } from "../lib/format";

const KIND_LABEL: Record<McpProposal["kind"], string> = {
  goal: "Goal",
  rule: "Rule",
  budget_move: "Budget move",
  recategorize: "Category change",
};

/**
 * Header badge for changes a connected app (Claude, ChatGPT) proposed over
 * MCP. Nothing happens until the user confirms one here. Hidden when there
 * are none; rechecked whenever the tab regains focus, since the proposals
 * arrive from outside the app.
 */
export function ProposalsTray({
  token,
  refreshKey,
  onChanged,
}: {
  token: string;
  refreshKey?: unknown;
  /** Called after a confirmed change, so the views can reload. */
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [proposals, setProposals] = useState<McpProposal[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let stale = false;
    const load = () =>
      fetchProposals(token)
        .then((p) => !stale && setProposals(p))
        .catch(() => {});
    load();
    window.addEventListener("focus", load);
    return () => {
      stale = true;
      window.removeEventListener("focus", load);
    };
  }, [token, refreshKey]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => !rootRef.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  async function resolve(p: McpProposal, confirm: boolean) {
    setBusyId(p.id);
    setErrors((e) => {
      const rest = { ...e };
      delete rest[p.id];
      return rest;
    });
    try {
      await (confirm ? confirmProposal(token, p.id) : dismissProposal(token, p.id));
      setProposals((list) => list.filter((x) => x.id !== p.id));
      if (confirm) onChanged();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Couldn't do that. Try again.";
      setErrors((e) => ({ ...e, [p.id]: message }));
    } finally {
      setBusyId(null);
    }
  }

  if (proposals.length === 0 && !open) return null;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label={`${proposals.length} proposed change${proposals.length === 1 ? "" : "s"} to review`}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex h-9 min-w-9 cursor-pointer items-center justify-center gap-1.5 rounded-full bg-signal-wash px-2.5 text-[13px] font-semibold text-signal hover:text-signal-hi sm:px-3"
      >
        <span className="font-tabular">{proposals.length}</span>
        <span className="hidden sm:inline">to review</span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Proposed changes"
          className="absolute right-0 top-12 z-50 flex max-h-[70vh] w-[min(380px,calc(100vw-32px))] flex-col overflow-hidden rounded-[20px] border border-line-strong bg-surface shadow-modal animate-drop"
        >
          <div className="border-b border-line px-4 py-3">
            <p className="m-0 text-sm font-semibold text-ink">Proposed changes</p>
            <p className="m-0 mt-0.5 text-xs text-ink-soft">From your connected apps. Nothing changes until you confirm.</p>
          </div>
          {proposals.length === 0 ? (
            <p className="m-0 px-4 py-8 text-center text-[13px] text-ink-soft">All caught up.</p>
          ) : (
            <ul className="m-0 list-none overflow-y-auto p-0">
              {proposals.map((p) => (
                <li key={p.id} className="flex flex-col gap-2.5 border-t border-line px-4 py-3 first:border-0">
                  <div>
                    <span className="font-mono text-[10px] tracking-[0.1em] text-ink-faint">
                      {KIND_LABEL[p.kind].toUpperCase()} · {p.source.toUpperCase()} · {formatRelativeTime(p.created_at)}
                    </span>
                    <p className="m-0 mt-0.5 text-[14px] text-ink">{p.summary}</p>
                    {errors[p.id] && <p className="m-0 mt-1 text-xs text-negative">{errors[p.id]}</p>}
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => resolve(p, true)}
                      disabled={busyId !== null}
                      className="h-9 flex-1 cursor-pointer rounded-[12px] bg-signal text-[13px] font-semibold text-bg hover:bg-signal-hi disabled:opacity-60"
                    >
                      {busyId === p.id ? "Saving…" : "Confirm"}
                    </button>
                    <button
                      type="button"
                      onClick={() => resolve(p, false)}
                      disabled={busyId !== null}
                      className="h-9 cursor-pointer rounded-[12px] px-3 text-[13px] text-ink-soft hover:text-ink disabled:opacity-60"
                    >
                      Dismiss
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
