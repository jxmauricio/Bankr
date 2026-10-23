import { createContext, useContext, useState, type ReactNode } from "react";
import { DEFAULT_PERIOD, type Period } from "@/lib/period";

/** One period shared by Cash flow and Transactions, like the web app's header filter. */
const PeriodContext = createContext<{ period: Period; setPeriod: (p: Period) => void } | null>(null);

export function PeriodProvider({ children }: { children: ReactNode }) {
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);
  return <PeriodContext.Provider value={{ period, setPeriod }}>{children}</PeriodContext.Provider>;
}

export function usePeriod() {
  const ctx = useContext(PeriodContext);
  if (!ctx) throw new Error("usePeriod must be used within PeriodProvider");
  return ctx;
}
