import { useEffect, useState } from "react";

let windowName = "this_month";
let tick = 0;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((fn) => fn());
}

/** The Budget tab's window: money left and the category list share it. */
export function useBudgetWindow(): [string, (next: string) => void] {
  const [value, setValue] = useState(windowName);
  useEffect(() => {
    const on = () => setValue(windowName);
    listeners.add(on);
    return () => {
      listeners.delete(on);
    };
  }, []);
  return [
    value,
    (next: string) => {
      windowName = next;
      emit();
    },
  ];
}

/** Bump after editing pay so Budget reloads money left. */
export function bumpMoneyLeft() {
  tick += 1;
  emit();
}

export function useMoneyLeftTick() {
  const [value, setValue] = useState(tick);
  useEffect(() => {
    const on = () => setValue(tick);
    listeners.add(on);
    return () => {
      listeners.delete(on);
    };
  }, []);
  return value;
}
