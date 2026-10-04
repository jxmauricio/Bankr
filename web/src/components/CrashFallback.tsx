export function CrashFallback() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="font-display text-xl font-semibold text-ink">Something went wrong</h1>
      <p className="max-w-xs text-sm text-ink-soft">Bankr hit an unexpected error. Reloading usually fixes it.</p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-strong cursor-pointer"
      >
        Reload
      </button>
    </div>
  );
}
