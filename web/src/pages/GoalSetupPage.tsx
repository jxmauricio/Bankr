import { useState, type FormEvent } from "react";
import { ApiError, createGoal } from "../lib/api";
import { useSession } from "../lib/session";
import { GOAL_KIND_HINTS, GOAL_KIND_LABELS, GOAL_KINDS, SPEND_CATEGORIES, TRACKING_WINDOWS, formatMoney } from "../lib/format";
import { GoalNameField } from "../components/GoalNameField";
import { SetupHeader, StepEyebrow } from "../components/SetupHeader";

const fieldClass =
  "h-12 w-full rounded-[10px] border border-control bg-surface px-3.5 text-[15px] text-ink outline-none focus:border-signal";
const labelClass = "mb-1.5 block text-[13px] text-ink-soft";

export function GoalSetupPage({ onGoalSet }: { onGoalSet: () => void }) {
  const { token } = useSession();
  const [type, setType] = useState<(typeof GOAL_KINDS)[number]>("save");
  const [name, setName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [category, setCategory] = useState("Dining");
  const [windowName, setWindowName] = useState("this_month");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const isTracker = type === "track_spending";

  function chooseKind(kind: (typeof GOAL_KINDS)[number]) {
    setType(kind);
    setName(kind === "track_spending" ? category : "");
    setError(null);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;

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
    <div className="flex min-h-screen flex-col">
      <SetupHeader step={2} />
      <div className="mx-auto flex w-full max-w-[1080px] flex-1 flex-wrap items-start gap-16 px-6 py-12 sm:px-8">
        <form onSubmit={handleSubmit} className="flex min-w-0 flex-[1_1_440px] flex-col gap-6">
          <StepEyebrow>STEP 2 OF 2</StepEyebrow>
          <h1 className="font-display text-[34px] font-normal leading-[1.08] tracking-[-0.02em] text-ink sm:text-[42px]">
            Set your first goal.
          </h1>

          <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <legend className="mb-2 text-[13px] text-ink-soft">Kind of goal</legend>
            {GOAL_KINDS.map((kind) => (
              <label
                key={kind}
                className={`flex cursor-pointer flex-col gap-1.5 rounded-xl border p-4 transition-colors ${
                  type === kind ? "border-signal bg-signal-wash" : "border-line-strong hover:border-control"
                }`}
              >
                <span className="flex items-center gap-2 text-[15px] font-medium text-ink">
                  <input
                    type="radio"
                    name="kind"
                    checked={type === kind}
                    onChange={() => chooseKind(kind)}
                    className="m-0 h-[18px] w-[18px] accent-signal"
                  />
                  {GOAL_KIND_LABELS[kind]}
                </span>
                <span className="text-[13px] leading-normal text-ink-soft">{GOAL_KIND_HINTS[kind]}</span>
              </label>
            ))}
          </fieldset>

          <GoalNameField
            id="setup-name"
            value={name}
            onChange={setName}
            suggestions={!isTracker}
            labelClassName={labelClass}
          />

          {isTracker ? (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label htmlFor="setup-category" className={labelClass}>
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
                    className={`${fieldClass} cursor-pointer`}
                  >
                    {SPEND_CATEGORIES.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="setup-cap" className={labelClass}>
                    Spending cap <span className="text-ink-faint">(optional)</span>
                  </label>
                  <MoneyInput id="setup-cap" value={targetAmount} onChange={setTargetAmount} placeholder="Just track" />
                </div>
              </div>
              <div>
                <p className={labelClass}>Time window</p>
                <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                  {TRACKING_WINDOWS.map((w) => (
                    <button
                      key={w.id}
                      type="button"
                      aria-pressed={windowName === w.id}
                      onClick={() => setWindowName(w.id)}
                      className={`min-h-11 cursor-pointer rounded-[10px] border px-3 text-left text-[13px] transition-colors ${
                        windowName === w.id
                          ? "border-signal bg-signal-wash text-ink"
                          : "border-line-strong text-ink-soft hover:border-control"
                      }`}
                    >
                      {w.label}
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="amount" className={labelClass}>
                  Target amount
                </label>
                <MoneyInput id="amount" value={targetAmount} onChange={setTargetAmount} placeholder="12,000" required />
              </div>
              <div>
                <label htmlFor="date" className={labelClass}>
                  By <span className="text-ink-faint">(optional)</span>
                </label>
                <input
                  id="date"
                  type="date"
                  value={targetDate}
                  onChange={(e) => setTargetDate(e.target.value)}
                  className={`${fieldClass} font-tabular [color-scheme:dark]`}
                />
              </div>
            </div>
          )}

          {error && (
            <p role="alert" className="text-sm text-negative">
              {error}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={isBusy}
              className="h-12 cursor-pointer rounded-[10px] bg-ink px-6 text-[15px] font-medium text-bg transition-opacity disabled:opacity-60"
            >
              {isBusy ? "Saving…" : isTracker ? "Start tracking" : "Create goal & start"}
            </button>
            <button
              type="button"
              onClick={onGoalSet}
              className="h-12 cursor-pointer rounded-[10px] px-4 text-[15px] text-ink-soft hover:text-ink"
            >
              Skip for now
            </button>
          </div>
        </form>

        <GoalPreview
          isTracker={isTracker}
          name={name.trim() || (isTracker ? category : "Your goal")}
          amount={Number(targetAmount) || 0}
          date={targetDate}
          windowLabel={TRACKING_WINDOWS.find((w) => w.id === windowName)?.label ?? ""}
        />
      </div>
    </div>
  );
}

function MoneyInput({
  id,
  value,
  onChange,
  placeholder,
  required,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  required?: boolean;
}) {
  return (
    <div className="flex h-12 items-center rounded-[10px] border border-control bg-surface px-3.5 focus-within:border-signal">
      <span className="mr-1 text-ink-faint">$</span>
      <input
        id={id}
        type="number"
        min={required ? "1" : "0"}
        step="0.01"
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="min-w-0 flex-1 bg-transparent text-right font-tabular text-[15px] text-ink outline-none focus-visible:outline-none"
      />
    </div>
  );
}

function GoalPreview({
  isTracker,
  name,
  amount,
  date,
  windowLabel,
}: {
  isTracker: boolean;
  name: string;
  amount: number;
  date: string;
  windowLabel: string;
}) {
  const byLabel = date
    ? `by ${new Date(`${date}T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" })}`
    : "no deadline";
  return (
    <aside aria-label="Preview" className="flex min-w-0 flex-[1_1_320px] flex-col gap-3.5">
      <span className="font-mono text-[11px] tracking-[0.14em] text-ink-faint">PREVIEW · HOW IT WILL LOOK</span>
      <div className="flex flex-col gap-3 rounded-3xl border border-line bg-surface p-[22px]">
        <div className="flex items-center justify-between gap-3">
          <span className="truncate text-[15px] font-medium text-ink">{name}</span>
          <span className="font-mono text-[10px] tracking-[0.1em] text-ink-faint">{isTracker ? "TRACK" : "SAVE"}</span>
        </div>
        <div className="flex justify-between font-tabular text-[13px] text-ink-soft">
          {isTracker ? (
            <>
              <span>
                <span className="text-ink">$0</span>
                {amount > 0 ? ` of ${formatMoney(amount)}` : " spent"}
              </span>
              <span>{windowLabel.toLowerCase()}</span>
            </>
          ) : (
            <>
              <span>
                <span className="text-ink">$0</span> of {amount > 0 ? formatMoney(amount) : "$—"}
              </span>
              <span>{byLabel}</span>
            </>
          )}
        </div>
        <div className="relative h-1.5 rounded-[3px] bg-line">
          <div className="absolute -top-[5px] left-0 h-4 w-0.5 bg-ink" />
        </div>
        <span className="text-xs text-ink-soft">● Starts today — pace begins tracking tomorrow</span>
      </div>
      <div className="flex flex-col gap-2.5 text-[13px] leading-normal text-ink-soft">
        <div className="flex items-start gap-2.5">
          <span className="mt-[7px] h-1.5 w-[18px] shrink-0 rounded-[3px] bg-ink-soft" />
          <span>{isTracker ? "The bar fills as you spend." : "The bar fills as you save."}</span>
        </div>
        <div className="flex items-start gap-2.5">
          <span className="mx-2 mt-0.5 h-4 w-0.5 shrink-0 bg-ink" />
          <span>
            {isTracker
              ? "The tick is how much of your cap you’d use at an even pace."
              : "The tick is where you should be today to finish on time."}
          </span>
        </div>
        <div className="flex items-start gap-2.5">
          <span className="mt-[7px] h-1.5 w-[18px] shrink-0 rounded-[3px] bg-positive" />
          <span>
            {isTracker ? "Short of the tick means under pace." : "Past the tick means ahead. Short of it shows how far behind."}
          </span>
        </div>
      </div>
      <p className="mt-1.5 text-xs text-ink-faint">You can have up to 5 goals.</p>
    </aside>
  );
}
