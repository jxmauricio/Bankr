import { useSyncExternalStore } from "react";

const STORAGE_KEY = "centsio_hide_numbers";

/** What a dollar amount reads as while numbers are hidden. */
export const HIDDEN_AMOUNT = "••••";

function read(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

let hidden = read();
const listeners = new Set<() => void>();

/** Plain function so the money formatters (not components) can ask. */
export function isHidden(): boolean {
  return hidden;
}

export function setHidden(next: boolean) {
  hidden = next;
  try {
    localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
  } catch {
    /* private mode */
  }
  listeners.forEach((l) => l());
}

/** A formatted dollar amount, or HIDDEN_AMOUNT while numbers are hidden. */
export function mask(text: string): string {
  return hidden ? HIDDEN_AMOUNT : text;
}

/**
 * The formatters read the flag directly, so a component only re-renders on a
 * change if something above it subscribes. PostSignInGate does, which
 * re-renders everything under it (nothing is memoized).
 */
export function useHideNumbers(): [boolean, (next: boolean) => void] {
  const value = useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    () => hidden,
  );
  return [value, setHidden];
}
