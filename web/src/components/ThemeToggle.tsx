import { useTheme } from "../lib/theme";

/** Sun/moon control for the top bar. Shows the mode you'll switch to. */
export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const toDark = theme === "light";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={toDark ? "Switch to dark mode" : "Switch to light mode"}
      title={toDark ? "Dark mode" : "Light mode"}
      className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-full text-ink-soft hover:bg-surface hover:text-ink"
    >
      {toDark ? <MoonIcon /> : <SunIcon />}
    </button>
  );
}

function MoonIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 14.3A8.5 8.5 0 1 1 9.7 3 7 7 0 0 0 21 14.3Z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}
