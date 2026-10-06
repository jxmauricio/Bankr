/** Wordmark plus the two-step onboarding progress (link accounts → first goal). */
export function SetupHeader({ step, linkedLabel }: { step: 1 | 2; linkedLabel?: string }) {
  const steps = [
    { n: 1, label: step > 1 ? (linkedLabel ?? "Accounts linked") : "Link accounts" },
    { n: 2, label: "First goal" },
  ];
  return (
    <header className="flex min-h-16 flex-wrap items-center justify-between gap-4 border-b border-line px-6 sm:px-8">
      <span className="font-display text-2xl font-semibold tracking-tight text-ink">
        bankr<span className="text-signal">_</span>
      </span>
      <ol aria-label="Setup progress" className="flex gap-6 text-[13px]">
        {steps.map(({ n, label }) => {
          const done = n < step;
          const current = n === step;
          return (
            <li
              key={n}
              aria-current={current ? "step" : undefined}
              className={`flex items-center gap-2 ${current ? "text-ink" : done ? "text-ink-soft" : "text-ink-faint"}`}
            >
              <span
                className={`flex h-[22px] w-[22px] items-center justify-center rounded-full font-mono text-[11px] ${
                  current ? "bg-ink text-bg" : done ? "bg-raised text-positive" : "border border-line-strong"
                }`}
              >
                {done ? "✓" : n}
              </span>
              {label}
            </li>
          );
        })}
      </ol>
    </header>
  );
}

export function StepEyebrow({ children }: { children: string }) {
  return <span className="font-mono text-[11px] tracking-[0.14em] text-signal">{children}</span>;
}
