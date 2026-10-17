import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useMoney } from "@/features/money/MoneyContext";
import { fetchTransactions, fetchTransactionsBetween, type TransactionList } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { DEFAULT_FILTERS, type Filters } from "./filtering";

interface FiltersValue {
  filters: Filters;
  update: (patch: Partial<Filters>) => void;
  /** The rows for the chosen dates, before any other filter. Shared with the filter sheets for their counts. */
  list: ReturnType<typeof useResource<TransactionList>>;
}

const FiltersContext = createContext<FiltersValue | null>(null);

/**
 * The Transactions tab's filters, held above the tabs so the filter sheets
 * (their own routes) and other screens (Cash flow opening a category) can set
 * them. Owns the fetch, since only the date range goes to the backend.
 */
export function TransactionFiltersProvider({ children }: { children: ReactNode }) {
  const { syncVersion } = useMoney();
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const update = useCallback((patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch })), []);

  const { date } = filters;
  const list = useResource(
    (token) => (date.kind === "custom" ? fetchTransactionsBetween(token, date.start, date.end) : fetchTransactions(token, date.window)),
    [JSON.stringify(date), syncVersion]
  );

  const value = useMemo(() => ({ filters, update, list }), [filters, update, list]);
  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>;
}

export function useTransactionFilters(): FiltersValue {
  const ctx = useContext(FiltersContext);
  if (!ctx) throw new Error("useTransactionFilters must be used within TransactionFiltersProvider");
  return ctx;
}
