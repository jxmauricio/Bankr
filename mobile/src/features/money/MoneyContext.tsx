import { createContext, useContext, type ReactNode } from "react";
import type { GoalProgressResponse, NetWorthHistory } from "@/lib/api";

/** Balances and goals the signed-in shell already loaded, shared with the net worth card and money sheet. */
export interface Money {
  netWorth: NetWorthHistory;
  goals: GoalProgressResponse;
  /** Re-reads balances and goals from the backend (no bank call). */
  refresh: () => Promise<void>;
  /** After linking a bank: re-reads balances and reloads every screen. */
  banksChanged: () => Promise<void>;
  /** Pulls fresh data from the banks, then re-reads everything. */
  syncFromBank: () => Promise<void>;
  isSyncing: boolean;
  syncError: string | null;
  /** Bumped after each successful sync; screens with their own data reload on it. */
  syncVersion: number;
}

const MoneyContext = createContext<Money | null>(null);

export function MoneyProvider({ value, children }: { value: Money; children: ReactNode }) {
  return <MoneyContext.Provider value={value}>{children}</MoneyContext.Provider>;
}

export function useMoney(): Money {
  const ctx = useContext(MoneyContext);
  if (!ctx) throw new Error("useMoney must be used within MoneyProvider");
  return ctx;
}

// Same threshold as the web app (web/src/components/StatusBanners.tsx).
const STALE_AFTER_MS = 36 * 3_600_000;

/** True when the last bank sync is old enough to be worth flagging. */
export function isStale(asOf: string | null | undefined): boolean {
  return Boolean(asOf) && Date.now() - new Date(asOf as string).getTime() > STALE_AFTER_MS;
}
