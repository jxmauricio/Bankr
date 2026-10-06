export type BootStep = { label: string; state: "done" | "active" | "waiting" };

/** First paint after sign-in: wordmark, an indeterminate bar, and what's loading. */
export function BootScreen({ steps }: { steps: BootStep[] }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div role="status" aria-live="polite" className="flex w-full max-w-[360px] flex-col gap-7">
        <span className="font-display text-4xl font-semibold tracking-[-0.03em] text-ink">
          bankr<span className="animate-caret text-signal">_</span>
        </span>
        <div className="flex flex-col gap-2.5">
          <span className="text-[15px] text-ink">Securely connecting to your accounts</span>
          <div className="h-[3px] overflow-hidden rounded-sm bg-line">
            <div className="animate-indeterminate h-[3px] w-2/5 rounded-sm bg-signal" />
          </div>
        </div>
        <ol className="flex flex-col gap-2 font-mono text-xs">
          {steps.map((step) => (
            <li
              key={step.label}
              className={`flex justify-between ${
                step.state === "done" ? "text-ink-soft" : step.state === "active" ? "text-ink" : "text-ink-faint"
              }`}
            >
              <span>{step.label}</span>
              <span
                aria-label={step.state === "done" ? "done" : step.state === "active" ? "in progress" : "waiting"}
                className={step.state === "done" ? "text-positive" : step.state === "active" ? "text-signal" : ""}
              >
                {step.state === "done" ? "✓" : step.state === "active" ? "●" : "○"}
              </span>
            </li>
          ))}
        </ol>
        <span className="text-xs leading-normal text-ink-faint">Read-only access via Plaid. Usually under 3 seconds.</span>
      </div>
    </div>
  );
}
