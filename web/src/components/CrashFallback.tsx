export function CrashFallback() {
  return (
    <div className="flex min-h-screen flex-col items-start justify-center gap-4 px-6 sm:mx-auto sm:max-w-md">
      <span className="font-display text-xl font-semibold tracking-tight text-ink">
        bankr<span className="text-signal">_</span>
      </span>
      <h1 className="font-display text-[28px] font-medium leading-tight tracking-tight text-ink">
        Something broke on our side.
      </h1>
      <p className="text-[15px] leading-relaxed text-ink-soft">
        This screen failed to load. Your accounts and data aren’t affected — Bankr can only read them.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="h-12 rounded-[14px] bg-accent px-5 text-sm font-semibold text-bg hover:bg-accent-strong cursor-pointer"
        >
          Reload
        </button>
        <a
          href="/"
          className="flex h-12 items-center rounded-[14px] bg-raised px-5 text-sm text-ink hover:text-signal-hi"
        >
          Back to home
        </a>
      </div>
    </div>
  );
}
