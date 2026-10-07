import { useCallback, useEffect, useState } from "react";

/** Home's three views. Kept in the URL hash so Back and a refresh land where you were. */
export type View = "chat" | "transactions" | "cashflow";

export const VIEWS: { id: View; label: string; key: string }[] = [
  { id: "chat", label: "Chat", key: "1" },
  { id: "transactions", label: "Transactions", key: "2" },
  { id: "cashflow", label: "Cash flow", key: "3" },
];

function fromHash(): View {
  const hash = window.location.hash.replace(/^#/, "");
  return VIEWS.some((v) => v.id === hash) ? (hash as View) : "chat";
}

/** True while the user is typing somewhere, so single-key shortcuts stay out of the way. */
export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

export function useView(): [View, (view: View) => void] {
  const [view, setViewState] = useState<View>(fromHash);

  const setView = useCallback((next: View) => {
    setViewState(next);
    const hash = next === "chat" ? "" : `#${next}`;
    if (window.location.hash !== hash) {
      history.pushState(null, "", hash || window.location.pathname + window.location.search);
    }
  }, []);

  useEffect(() => {
    const onHash = () => setViewState(fromHash());
    window.addEventListener("popstate", onHash);
    window.addEventListener("hashchange", onHash);
    return () => {
      window.removeEventListener("popstate", onHash);
      window.removeEventListener("hashchange", onHash);
    };
  }, []);

  // 1 / 2 / 3 switch views, unless a field has focus or a dialog is open.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      const match = VIEWS.find((v) => v.key === e.key);
      if (match) {
        e.preventDefault();
        setView(match.id);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setView]);

  return [view, setView];
}
