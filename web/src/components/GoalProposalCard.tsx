import { useState, type FormEvent } from "react";
import { ApiError, createGoal, type GoalProposal } from "../lib/api";
import { SPEND_CATEGORIES, TRACKING_WINDOWS } from "../lib/format";
import { GoalNameField } from "./GoalNameField";

type CardStatus = "pending" | "created" | "dismissed";

const LEGACY_SAVE_NAMES: Record<string, string> = {
  save_amount: "Savings goals",
  pay_off_debt: "Paying off debt",
  build_emergency_fund: "Emergency fund",
};

function isTracker(type: string) {
  return type === "track_spending";
}

function defaultSaveName(proposal: GoalProposal): string {
  if (proposal.name?.trim()) return proposal.name.trim();
  return LEGACY_SAVE_NAMES[proposal.type] ?? "";
}

export function GoalProposalCard({
  token,
  proposal,
  initialStatus = "pending",
  onCreated,
}: {
  token: string | null;
  proposal: GoalProposal;
  initialStatus?: CardStatus;
  onCreated: () => void | Promise<void>;
}) {
  if (isTracker(proposal.type)) {
    return (
      <SpendingTrackerProposalCard
        token={token}
        proposal={proposal}
        initialStatus={initialStatus}
        onCreated={onCreated}
      />
    );
  }
  return (
    <SavingsGoalProposalCard token={token} proposal={proposal} initialStatus={initialStatus} onCreated={onCreated} />
  );
}

function SavingsGoalProposalCard({
  token,
  proposal,
  initialStatus,
  onCreated,
}: {
  token: string | null;
  proposal: GoalProposal;
  initialStatus: CardStatus;
  onCreated: () => void | Promise<void>;
}) {
  const [name, setName] = useState(defaultSaveName(proposal));
  const [targetAmount, setTargetAmount] = useState(
    proposal.target_amount > 0 ? String(proposal.target_amount) : "",
  );
  const [targetDate, setTargetDate] = useState(proposal.target_date ?? "");
  const [status, setStatus] = useState<CardStatus>(initialStatus);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  if (status === "dismissed") return null;

  if (status === "created") {
    return (
      <div className="max-w-[85%] rounded-xl border border-border bg-surface p-4">
        <p className="text-sm text-ink-soft">Goal set — it’s on the left.</p>
      </div>
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
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
      setStatus("created");
      await onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your goal. Try again.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-[85%] space-y-3 rounded-xl border border-border bg-surface p-4">
      <div>
        <p className="text-sm font-medium text-ink">Create this savings goal?</p>
        <p className="mt-0.5 text-xs text-ink-faint">
          {proposal.at_limit
            ? "You already have 5 goals — finish or drop one before adding another."
            : "Name it, set a target, and it’ll show up on the left."}
        </p>
      </div>

      <GoalNameField
        id={`proposal-name-${proposal.target_amount}`}
        value={name}
        onChange={setName}
        suggestions
      />

      <div>
        <label htmlFor={`proposal-amount-${proposal.target_amount}`} className="mb-1 block text-xs font-medium text-ink-soft">
          Target amount
        </label>
        <div className="flex items-center rounded-lg border border-border bg-bg px-3 focus-within:border-accent">
          <span className="font-tabular text-ink-faint">$</span>
          <input
            id={`proposal-amount-${proposal.target_amount}`}
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
        <label htmlFor={`proposal-date-${proposal.target_amount}`} className="mb-1 block text-xs font-medium text-ink-soft">
          Target date <span className="text-ink-faint">(optional)</span>
        </label>
        <input
          id={`proposal-date-${proposal.target_amount}`}
          type="date"
          value={targetDate}
          onChange={(e) => setTargetDate(e.target.value)}
          className="w-full rounded-lg border border-border bg-bg px-3 py-2 font-tabular text-sm text-ink outline-none focus:border-accent"
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <CardActions
        atLimit={Boolean(proposal.at_limit)}
        isBusy={isBusy}
        busyLabel="Saving…"
        confirmLabel="Set goal"
        onDismiss={() => setStatus("dismissed")}
      />
    </form>
  );
}

function SpendingTrackerProposalCard({
  token,
  proposal,
  initialStatus,
  onCreated,
}: {
  token: string | null;
  proposal: GoalProposal;
  initialStatus: CardStatus;
  onCreated: () => void | Promise<void>;
}) {
  const [category, setCategory] = useState(proposal.category ?? "Dining");
  const [name, setName] = useState(proposal.name?.trim() || proposal.category || "Dining");
  const [windowName, setWindowName] = useState(proposal.window ?? "this_month");
  const [budget, setBudget] = useState(proposal.target_amount > 0 ? String(proposal.target_amount) : "");
  const [status, setStatus] = useState<CardStatus>(initialStatus);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  if (status === "dismissed") return null;

  if (status === "created") {
    return (
      <div className="max-w-[85%] rounded-xl border border-border bg-surface p-4">
        <p className="text-sm text-ink-soft">Tracking {name || category} — it’s on the left.</p>
      </div>
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    const amount = budget.trim() === "" ? 0 : Number(budget);
    if (budget.trim() !== "" && (!Number.isFinite(amount) || amount < 0)) {
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
      setStatus("created");
      await onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save this tracker. Try again.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-[85%] space-y-3 rounded-xl border border-border bg-surface p-4">
      <div>
        <p className="text-sm font-medium text-ink">Track this spending?</p>
        <p className="mt-0.5 text-xs text-ink-faint">
          {proposal.at_limit
            ? "You already have 5 goals — finish or drop one before adding another."
            : "Pick what to watch and over how long. It’ll sit on the left with your other goals."}
        </p>
      </div>

      <GoalNameField id="tracker-proposal-name" value={name} onChange={setName} />

      <div>
        <label htmlFor="tracker-category" className="mb-1 block text-xs font-medium text-ink-soft">
          What to track
        </label>
        <select
          id="tracker-category"
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
                windowName === w.id ? "border-accent bg-accent-soft text-ink" : "border-border bg-bg text-ink-soft hover:border-ink-faint"
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label htmlFor="tracker-budget" className="mb-1 block text-xs font-medium text-ink-soft">
          Spending cap <span className="text-ink-faint">(optional)</span>
        </label>
        <div className="flex items-center rounded-lg border border-border bg-bg px-3 focus-within:border-accent">
          <span className="font-tabular text-ink-faint">$</span>
          <input
            id="tracker-budget"
            type="number"
            min="0"
            step="0.01"
            placeholder="Just track"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            className="w-full bg-transparent py-2 pl-1.5 font-tabular text-sm text-ink outline-none"
          />
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <CardActions
        atLimit={Boolean(proposal.at_limit)}
        isBusy={isBusy}
        busyLabel="Saving…"
        confirmLabel="Start tracking"
        onDismiss={() => setStatus("dismissed")}
      />
    </form>
  );
}

function CardActions({
  atLimit,
  isBusy,
  busyLabel,
  confirmLabel,
  onDismiss,
}: {
  atLimit: boolean;
  isBusy: boolean;
  busyLabel: string;
  confirmLabel: string;
  onDismiss: () => void;
}) {
  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={onDismiss}
        className="flex-1 rounded-lg border border-border py-2 text-sm text-ink-soft transition-colors hover:border-ink-faint hover:text-ink cursor-pointer"
      >
        Not now
      </button>
      <button
        type="submit"
        disabled={isBusy || atLimit}
        className="flex-1 rounded-lg bg-accent py-2 text-sm font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-60 cursor-pointer"
      >
        {isBusy ? busyLabel : confirmLabel}
      </button>
    </div>
  );
}
