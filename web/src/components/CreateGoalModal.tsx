import { useEffect, useState, type FormEvent } from "react";
import { ApiError, createGoal } from "../lib/api";
import { GOAL_KIND_HINTS, GOAL_KIND_LABELS, GOAL_KINDS, SPEND_CATEGORIES, TRACKING_WINDOWS } from "../lib/format";
import { GoalNameField } from "./GoalNameField";

export function CreateGoalModal({
  token,
  atLimit,
  onClose,
  onCreated,
}: {
  token: string;
  atLimit: boolean;
  onClose: () => void;
  onCreated: () => void | Promise<void>;
}) {
  const [type, setType] = useState<string>("save");
  const [name, setName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [category, setCategory] = useState("Dining");
  const [windowName, setWindowName] = useState("this_month");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const isTracker = type === "track_spending";

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !isBusy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, isBusy]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (atLimit) return;

    if (isTracker) {
      const amount = targetAmount.trim() === "" ? 0 : Number(targetAmount);
      if (targetAmount.trim() !== "" && (!Number.isFinite(amount) || amount < 0)) {
        setError("Enter a budget of $0 or more, or leave it blank.");
        return;
      }
      setError(null);
      setIsBusy(true);
      try {
        await createGoal(token, {
          type: "track_spending",
          name: name.trim() || undefined,
          target_amount: amount,
          category,
          window: windowName,
        });
        await onCreated();
        onClose();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Couldn't save this tracker. Try again.");
      } finally {
        setIsBusy(false);
      }
      return;
    }

    const amount = Number(targetAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Enter a target amount greater than $0.");
      return;
    }
    setError(null);
    setIsBusy(true);
    try {
      await createGoal(token, {
        type: "save",
        name: name.trim() || undefined,
        target_amount: amount,
        target_date: targetDate || null,
      });
      await onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your goal. Try again.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={() => {
        if (!isBusy) onClose();
      }}
      role="presentation"
    >
      <form
        onSubmit={handleSubmit}
        className="max-h-[90vh] w-full max-w-sm overflow-y-auto rounded-2xl border border-border bg-surface p-6"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-goal-title"
      >
        <h2 id="create-goal-title" className="font-display text-lg font-semibold text-ink">
          New goal
        </h2>
        <p className="mt-1 text-sm text-ink-soft">
          {atLimit
            ? "You already have 5 goals — finish or drop one before adding another."
            : "Save toward something, or track spending in a category."}
        </p>

        <div className="mt-4 space-y-2">
          {GOAL_KINDS.map((kind) => (
            <button
              key={kind}
              type="button"
              onClick={() => {
                setType(kind);
                setError(null);
                setTargetAmount("");
                setName(kind === "track_spending" ? category : "");
              }}
              className={`w-full rounded-lg border p-3 text-left transition-colors cursor-pointer ${
                type === kind ? "border-accent bg-accent-soft" : "border-border bg-bg hover:border-ink-faint"
              }`}
            >
              <div className="text-sm font-medium text-ink">{GOAL_KIND_LABELS[kind]}</div>
              <div className="mt-0.5 text-xs text-ink-soft">{GOAL_KIND_HINTS[kind]}</div>
            </button>
          ))}
        </div>

        {isTracker ? (
          <div className="mt-4 space-y-3">
            <GoalNameField id="new-goal-name" value={name} onChange={setName} />
            <div>
              <label htmlFor="new-goal-category" className="mb-1 block text-xs font-medium text-ink-soft">
                What to track
              </label>
              <select
                id="new-goal-category"
                value={category}
                onChange={(e) => {
                  const next = e.target.value;
                  setName((current) => (!current.trim() || current === category ? next : current));
                  setCategory(next);
                }}
                className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-accent cursor-pointer"
              >
                {SPEND_CATEGORIES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <p className="mb-1 text-xs font-medium text-ink-soft">Time window</p>
              <div className="grid grid-cols-2 gap-1.5">
                {TRACKING_WINDOWS.map((w) => (
                  <button
                    key={w.id}
                    type="button"
                    onClick={() => setWindowName(w.id)}
                    className={`rounded-lg border px-2.5 py-2 text-left text-xs transition-colors cursor-pointer ${
                      windowName === w.id
                        ? "border-accent bg-accent-soft text-ink"
                        : "border-border bg-bg text-ink-soft hover:border-ink-faint"
                    }`}
                  >
                    {w.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label htmlFor="new-goal-cap" className="mb-1 block text-xs font-medium text-ink-soft">
                Spending cap <span className="text-ink-faint">(optional)</span>
              </label>
              <div className="flex items-center rounded-lg border border-border bg-bg px-3 focus-within:border-accent">
                <span className="font-tabular text-ink-faint">$</span>
                <input
                  id="new-goal-cap"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="Just track"
                  value={targetAmount}
                  onChange={(e) => setTargetAmount(e.target.value)}
                  className="w-full bg-transparent py-2 pl-1.5 font-tabular text-sm text-ink outline-none"
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            <GoalNameField id="new-goal-name" value={name} onChange={setName} suggestions />
            <div>
              <label htmlFor="new-goal-amount" className="mb-1 block text-xs font-medium text-ink-soft">
                Target amount
              </label>
              <div className="flex items-center rounded-lg border border-border bg-bg px-3 focus-within:border-accent">
                <span className="font-tabular text-ink-faint">$</span>
                <input
                  id="new-goal-amount"
                  type="number"
                  min="1"
                  step="0.01"
                  required
                  value={targetAmount}
                  onChange={(e) => setTargetAmount(e.target.value)}
                  className="w-full bg-transparent py-2 pl-1.5 font-tabular text-sm text-ink outline-none"
                />
              </div>
            </div>
            <div>
              <label htmlFor="new-goal-date" className="mb-1 block text-xs font-medium text-ink-soft">
                Target date <span className="text-ink-faint">(optional)</span>
              </label>
              <input
                id="new-goal-date"
                type="date"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
                className="w-full rounded-lg border border-border bg-bg px-3 py-2 font-tabular text-sm text-ink outline-none focus:border-accent"
              />
            </div>
          </div>
        )}

        {error && (
          <p role="alert" className="mt-3 text-sm text-danger">
            {error}
          </p>
        )}

        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isBusy}
            className="flex-1 rounded-lg border border-border py-2 text-sm text-ink-soft transition-colors hover:border-ink-faint hover:text-ink disabled:opacity-60 cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isBusy || atLimit}
            className="flex-1 rounded-lg bg-accent py-2 text-sm font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-60 cursor-pointer"
          >
            {isBusy ? "Saving…" : isTracker ? "Start tracking" : "Set goal"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function NewGoalButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-border bg-surface px-3 py-3 text-sm font-medium text-ink-soft transition-colors hover:border-accent hover:bg-accent-soft hover:text-ink cursor-pointer"
    >
      <PlusIcon />
      New goal
    </button>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  );
}
