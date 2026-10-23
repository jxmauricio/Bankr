import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

const STORAGE_KEY = "bankr_theme";

export type Theme = "light" | "dark";

function read(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

const ThemeContext = createContext<{
  theme: Theme;
  toggle: () => void;
} | null>(null);

/** Remembers light/dark and paints <html data-theme> so CSS tokens swap. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(read);
  const value = useMemo(
    () => ({
      theme,
      toggle: () => {
        const next: Theme = theme === "dark" ? "light" : "dark";
        setTheme(next);
        apply(next);
        try {
          localStorage.setItem(STORAGE_KEY, next);
        } catch {
          /* private mode */
        }
      },
    }),
    [theme],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme needs ThemeProvider");
  return ctx;
}
