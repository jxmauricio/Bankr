import { VIEWS, type View } from "../lib/useView";

function ViewIcon({ view, size = 17 }: { view: View; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (view === "chat") {
    return (
      <svg {...common}>
        <path d="M4 5h16v11H9l-5 4V5Z" />
      </svg>
    );
  }
  if (view === "transactions") {
    return (
      <svg {...common}>
        <path d="M8 6h12M8 12h12M8 18h12" />
        <circle cx="4" cy="6" r="1" />
        <circle cx="4" cy="12" r="1" />
        <circle cx="4" cy="18" r="1" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M3 6c8 0 8 6 18 6M3 6c8 0 8 12 18 12M3 6c8 0 10-2 18-2" />
    </svg>
  );
}

/** Desktop: a segmented control in the middle of the top bar, with its 1·2·3 shortcuts. */
export function ViewTabs({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return (
    <nav aria-label="Views" className="flex gap-1 rounded-[18px] border border-line bg-surface p-1">
      {VIEWS.map((v) => {
        const current = v.id === view;
        return (
          <button
            key={v.id}
            type="button"
            aria-current={current ? "page" : undefined}
            aria-keyshortcuts={v.key}
            onClick={() => onChange(v.id)}
            className={`flex h-11 cursor-pointer items-center gap-2 rounded-[14px] px-[18px] text-sm font-medium transition-colors ${
              current ? "bg-raised text-ink" : "text-ink-soft hover:text-ink"
            }`}
          >
            <ViewIcon view={v.id} />
            <span>{v.label}</span>
            <span className="font-mono text-[10px] text-ink-faint">{v.key}</span>
          </button>
        );
      })}
    </nav>
  );
}

/** Phones: a bottom tab bar that clears the home indicator. */
export function ViewTabBar({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return (
    <nav
      aria-label="Views"
      className="grid shrink-0 grid-cols-3 border-t border-line bg-bg px-2 pb-[max(10px,env(safe-area-inset-bottom))] pt-1.5 lg:hidden"
    >
      {VIEWS.map((v) => {
        const current = v.id === view;
        return (
          <button
            key={v.id}
            type="button"
            aria-current={current ? "page" : undefined}
            onClick={() => onChange(v.id)}
            className={`flex h-[52px] cursor-pointer flex-col items-center justify-center gap-1 ${current ? "text-ink" : "text-ink-faint"}`}
          >
            <span className={`flex h-[26px] w-11 items-center justify-center rounded-[13px] ${current ? "bg-raised" : ""}`}>
              <ViewIcon view={v.id} size={18} />
            </span>
            <span className="text-[11px] font-medium">{v.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
