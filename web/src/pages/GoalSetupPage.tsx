import { useState, type FormEvent } from "react";
import { ApiError, createGoal } from "../lib/api";
import { useSession } from "../lib/session";
import { GOAL_KIND_HINTS, GOAL_KIND_LABELS, GOAL_KINDS, SPEND_CATEGORIES, TRACKING_WINDOWS } from "../lib/format";
import { GoalNameField } from "../components/GoalNameField";

export function GoalSetupPage({ onGoalSet }: { onGoalSet: () => void }) {
  const { token } = useSession();
  const [type, setType] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [category, setCategory] = useState("Dining");
  const [windowName, setWindowName] = useState("this_month");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const isTracker = type === "track_spending";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !type) return;

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
        onGoalSet();
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
      onGoalSet();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your goal. Try again.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="font-display text-2xl font-semibold text-ink">What's your goal?</h1>
          <p className="mt-2 text-ink-soft">Save toward something, or track spending. You can add more later.</p>
        </div>

        <div className="space-y-2.5">
          {GOAL_KINDS.map((kind) => (
            <button
              key={kind}
              type="button"
              onClick={() => {
                setType(kind);
                setName(kind === "track_spending" ? category : "");
                setError(null);
              }}
              className={`w-full rounded-xl border p-4 text-left transition-colors cursor-pointer ${
                type === kind ? "border-accent bg-accent-soft" : "border-border bg-surface hover:border-ink-faint"
              }`}
            >
              <div className="font-medium text-ink">{GOAL_KIND_LABELS[kind]}</div>
              <div className="mt-0.5 text-sm text-ink-soft">{GOAL_KIND_HINTS[kind]}</div>
            </button>
          ))}
        </div>

        {type && (
          <form onSubmit={handleSubmit} className="mt-6 space-y-4 rounded-xl border border-border bg-surface p-4">
            <GoalNameField
              id="setup-name"
              value={name}
              onChange={setName}
              suggestions={!isTracker}
              labelClassName="mb-1.5 block text-sm font-medium text-ink-soft"
            />

            {isTracker ? (
              <>
                <div>
                  <label htmlFor="setup-category" className="mb-1.5 block text-sm font-medium text-ink-soft">
                    What to track
                  </label>
                  <select
                    id="setup-category"
                    value={category}
                    onChange={(e) => {
                      const next = e.target.value;
                      setName((current) => (!current.trim() || current === category ? next : current));
                      setCategory(next);
                    }}
                    className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft cursor-pointer"
                  >
                    {SPEND_CATEGORIES.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <p className="mb-1.5 text-sm font-medium text-ink-soft">Time window</p>
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
                  <label htmlFor="setup-cap" className="mb-1.5 block text-sm font-medium text-ink-soft">
                    Spending cap <span className="text-ink-faint">(optional)</span>
                  </label>
                  <div className="flex items-center rounded-lg border border-border bg-surface px-3 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent-soft">
                    <span className="font-tabular text-ink-faint">$</span>
                    <input
                      id="setup-cap"
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="Just track"
                      value={targetAmount}
                      onChange={(e) => setTargetAmount(e.target.value)}
                      className="w-full bg-transparent py-2 pl-1.5 font-tabular text-ink outline-none"
                    />
                  </div>
                </div>
              </>
            ) : (
              <>
                <div>
                  <label htmlFor="amount" className="mb-1.5 block text-sm font-medium text-ink-soft">
                    Target amount
                  </label>
                  <div className="flex items-center rounded-lg border border-border bg-surface px-3 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent-soft">
                    <span className="font-tabular text-ink-faint">$</span>
                    <input
                      id="amount"
                      type="number"
                      min="1"
                      step="0.01"
                      required
                      value={targetAmount}
                      onChange={(e) => setTargetAmount(e.target.value)}
                      className="w-full bg-transparent py-2 pl-1.5 font-tabular text-ink outline-none"
                      placeholder="6,000"
                    />
                  </div>
                </div>
                <div>
                  <label htmlFor="date" className="mb-1.5 block text-sm font-medium text-ink-soft">
                    Target date <span className="text-ink-faint">(optional)</span>
                  </label>
                  <input
                    id="date"
                    type="date"
                    value={targetDate}
                    onChange={(e) => setTargetDate(e.target.value)}
                    className="w-full rounded-lg border border-border bg-surface px-3 py-2 font-tabular text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft"
                  />
                </div>
              </>
            )}

            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={isBusy}
              className="w-full rounded-lg bg-accent py-2.5 font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-60 cursor-pointer"
            >
              {isBusy ? "Saving…" : isTracker ? "Start tracking" : "Set goal"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
