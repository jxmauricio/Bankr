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
  if (view === "health") {
    return (
      <svg {...common}>
        <path d="M3 12h4l2-6 3 12 2-6h7" />
      </svg>
    );
  }
  if (view === "plan") {
    return (
      <svg {...common}>
        <rect x="4" y="5" width="16" height="15" rx="2" />
        <path d="M4 10h16M9 3v4M15 3v4" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M3 6c8 0 8 6 18 6M3 6c8 0 8 12 18 12M3 6c8 0 10-2 18-2" />
    </svg>
  );
}

/** Desktop: text pills in the middle of the top bar, the open one filled (keys 1–4 still switch). */
export function ViewTabs({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return (
    <nav aria-label="Views" className="flex gap-1">
      {VIEWS.map((v) => {
        const current = v.id === view;
        return (
          <button
            key={v.id}
            type="button"
            aria-current={current ? "page" : undefined}
            aria-keyshortcuts={v.key}
            title={`${v.label} (${v.key})`}
            onClick={() => onChange(v.id)}
            className={`flex h-9 cursor-pointer items-center rounded-full px-4 text-[15px] transition-colors ${
              current ? "bg-signal font-semibold text-on-signal" : "font-medium text-ink-soft hover:bg-raised hover:text-ink"
            }`}
          >
            {v.label}
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
      className="grid shrink-0 grid-cols-5 border-t border-line bg-bg px-2 pb-[max(10px,env(safe-area-inset-bottom))] pt-1.5 lg:hidden"
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
