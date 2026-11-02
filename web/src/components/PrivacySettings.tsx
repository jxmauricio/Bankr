import { useHideNumbers } from "../lib/privacy";

/** Settings section: blank out dollar amounts on this device. */
export function PrivacySettings() {
  const [hidden, setHidden] = useHideNumbers();
  return (
    <>
      <h3 className="mt-5 text-sm font-medium text-ink-soft">Privacy</h3>
      <div className="mt-2 flex items-center justify-between gap-3 py-1.5">
        <div className="min-w-0">
          <p className="text-sm text-ink">Hide numbers</p>
          <p className="text-xs text-ink-faint">Dollar amounts show as •••• on this device.</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={hidden}
          aria-label="Hide numbers"
          onClick={() => setHidden(!hidden)}
          className={`relative h-6 w-10 shrink-0 cursor-pointer rounded-full transition-colors ${hidden ? "bg-signal" : "bg-line-strong"}`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-[left] ${hidden ? "left-[18px]" : "left-0.5"}`}
          />
        </button>
      </div>
    </>
  );
}
