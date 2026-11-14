import { useEffect, useState } from "react";

export type TransactionsPage = "recurring" | "activity";

let page: TransactionsPage = "recurring";
let recurringTick = 0;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((fn) => fn());
}

/** Recurring vs the line-by-line list on the Transactions tab. */
export function useTransactionsPage(): [TransactionsPage, (next: TransactionsPage) => void] {
  const [value, setValue] = useState(page);
  useEffect(() => {
    const on = () => setValue(page);
    listeners.add(on);
    return () => {
      listeners.delete(on);
    };
  }, []);
  return [
    value,
    (next: TransactionsPage) => {
      page = next;
      emit();
    },
  ];
}

/** Deep links from Budget/Home land on the line-by-line list. */
export function openActivity() {
  page = "activity";
  emit();
}

/** Reload the Recurring list after an edit. */
export function bumpRecurring() {
  recurringTick += 1;
  emit();
}

export function useRecurringTick() {
  const [value, setValue] = useState(recurringTick);
  useEffect(() => {
    const on = () => setValue(recurringTick);
    listeners.add(on);
    return () => {
      listeners.delete(on);
    };
  }, []);
  return value;
}
