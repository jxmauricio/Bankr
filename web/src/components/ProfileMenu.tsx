import { useEffect, useState } from "react";
import { fetchProfile } from "../lib/api";

const ITEM =
  "block w-full rounded-xl px-3 py-2.5 text-left text-sm text-ink transition-colors hover:bg-surface cursor-pointer";

// Opens on hover, and on keyboard focus so it isn't mouse-only.
export function ProfileMenu({
  token,
  onOpenSettings,
  onSignOut,
  attention = false,
}: {
  token: string;
  onOpenSettings: () => void;
  onSignOut: () => void;
  attention?: boolean;
}) {
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    fetchProfile(token)
      .then((p) => setEmail(p.email))
      .catch(() => setEmail(null));
  }, [token]);

  return (
    <div className="group relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-label={`Profile menu${email ? `, ${email}` : ""}`}
        className="flex h-11 items-center gap-1.5 rounded-full bg-surface pl-1 pr-2 cursor-pointer"
      >
        <span className="relative flex h-9 w-9 items-center justify-center rounded-full bg-raised text-[13px] font-semibold text-ink">
          {(email ?? "?").slice(0, 2).toUpperCase()}
          {attention && (
            <span
              role="img"
              aria-label="A bank needs attention"
              className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-negative ring-2 ring-surface"
            />
          )}
        </span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-soft)" strokeWidth="1.7" strokeLinecap="round" aria-hidden>
          <path d="m7 10 5 5 5-5" />
        </svg>
      </button>
      {/* pt-2 (not margin) keeps the pointer inside the group while crossing the gap. */}
      <div className="invisible absolute right-0 top-full z-10 pt-2 opacity-0 transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100">
        <div role="menu" className="w-64 rounded-[20px] border border-line bg-raised p-1.5 shadow-menu">
          <div className="px-3 py-2">
            <div className="text-xs text-ink-faint">Signed in as</div>
            <div className="truncate text-sm text-ink">{email ?? "…"}</div>
          </div>
          <div className="my-1 border-t border-border" />
          <a href="/profile" role="menuitem" className={ITEM}>
            View profile
          </a>
          <button type="button" role="menuitem" onClick={onOpenSettings} className={ITEM}>
            Settings
          </button>
          <button type="button" role="menuitem" onClick={onSignOut} className={ITEM}>
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
