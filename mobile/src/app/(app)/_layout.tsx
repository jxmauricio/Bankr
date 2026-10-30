import { Stack } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";
import {
  ApiError,
  fetchGoalProgress,
  fetchNetWorth,
  resyncAccounts,
  type GoalProgressResponse,
  type NetWorthHistory,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { loadCategories } from "@/lib/useCategories";
import { MoneyProvider } from "@/features/money/MoneyContext";
import { BankLogosProvider } from "@/features/bank/BankLogos";
import { LinkBankScreen } from "@/features/bank/LinkBankScreen";
import { NotificationsProvider } from "@/features/notifications/NotificationsContext";
import { PeriodProvider } from "@/features/period/PeriodContext";
import { TransactionFiltersProvider } from "@/features/transactions/FiltersContext";
import { useColors } from "@/theme/theme";
import { Button, ComingSoon, ErrorState, Loading, Screen } from "@/ui";

// Plaid refreshes from the bank only a few times a day and webhooks push the
// rest, so polling faster than this mostly finds nothing new.
const BACKGROUND_SYNC_MS = 5 * 60 * 1000;
// Coming back to the app syncs only if the last sync is older than this.
const RESYNC_ON_RETURN_MS = 60 * 1000;

type Gate =
  | { step: "loading" }
  | { step: "load-failed" }
  | { step: "link-bank" | "set-goal" }
  | { step: "home"; netWorth: NetWorthHistory; goals: GoalProgressResponse };

/**
 * Same onboarding gate as the web app's PostSignInGate: no balances means no
 * bank yet, no goals means goal setup, otherwise the tabs.
 */
export default function SignedInLayout() {
  const colors = useColors();
  const { token, signOut } = useSession();
  const [gate, setGate] = useState<Gate>({ step: "loading" });

  // Bumped to run the gate again; the effect below is the only place it runs.
  const [attempt, setAttempt] = useState(0);
  const onRefreshed = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    // Categories too: chart colors, before any chart renders.
    Promise.all([fetchNetWorth(token), fetchGoalProgress(token), loadCategories(token)])
      .then(
        ([netWorth, goals]) => {
          if (cancelled) return;
          if (netWorth.current === null) setGate({ step: "link-bank" });
          else if (!goals.goals?.length) setGate({ step: "set-goal" });
          else setGate({ step: "home", netWorth, goals });
        },
        (err: unknown) => {
          if (cancelled) return;
          if (err instanceof ApiError && err.status === 401) return signOut();
          // A failed background refresh keeps what's on screen.
          setGate((g) => (g.step === "home" ? g : { step: "load-failed" }));
        }
      )
      .finally(() => {
        onRefreshed.current?.();
        onRefreshed.current = null;
      });
    return () => {
      cancelled = true;
    };
  }, [token, signOut, attempt]);

  const retry = () => {
    setGate({ step: "loading" });
    setAttempt((n) => n + 1);
  };

  /** Re-reads balances and goals without leaving the tabs; resolves when done. */
  const refresh = useCallback(
    () =>
      new Promise<void>((resolve) => {
        onRefreshed.current = resolve;
        setAttempt((n) => n + 1);
      }),
    []
  );

  const [isSyncing, setIsSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncVersion, setSyncVersion] = useState(0);

  // One POST /linked-accounts/sync at a time. Extra taps wait for it instead of
  // no-oping (the launch/return silent sync used to swallow the refresh button).
  const syncInFlight = useRef(false);
  const syncWaiters = useRef<(() => void)[]>([]);
  const visibleSyncs = useRef(0);
  const lastSyncAt = useRef(0);

  /**
   * Same as the web app's syncFromBank: POST /linked-accounts/sync (Plaid pull
   * for every linked bank), then re-read balances, goals and transactions.
   * Silent syncs (automatic ones) show no spinner and no error. A tap while one
   * is already running shows the spinner and waits for that same request.
   */
  const syncFromBank = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}) => {
      if (!token) return;
      if (!silent) {
        visibleSyncs.current += 1;
        setIsSyncing(true);
        setSyncError(null);
      }
      try {
        if (syncInFlight.current) {
          await new Promise<void>((resolve) => {
            syncWaiters.current.push(resolve);
          });
          return;
        }
        syncInFlight.current = true;
        try {
          await resyncAccounts(token);
          lastSyncAt.current = Date.now();
          try {
            await refresh();
          } finally {
            // Transactions, cash flow and health key off this even if the
            // net-worth re-read fails after a successful bank pull.
            setSyncVersion((n) => n + 1);
          }
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) return signOut();
          if (!silent) setSyncError(err instanceof ApiError ? err.message : "Couldn't refresh from your bank. Try again.");
        } finally {
          syncInFlight.current = false;
          const waiting = syncWaiters.current.splice(0);
          waiting.forEach((w) => w());
        }
      } finally {
        if (!silent) {
          visibleSyncs.current -= 1;
          if (visibleSyncs.current === 0) setIsSyncing(false);
        }
      }
    },
    [token, refresh, signOut]
  );

  // Once home is up: sync right away, again on coming back to the app if the
  // last one is stale, and every 5 minutes while the app is in the foreground.
  const isHome = gate.step === "home";
  useEffect(() => {
    if (!isHome) return;
    const syncIfStale = () => {
      if (Date.now() - lastSyncAt.current > RESYNC_ON_RETURN_MS) syncFromBank({ silent: true });
    };
    syncIfStale();
    const timer = setInterval(() => {
      if (AppState.currentState === "active") syncFromBank({ silent: true });
    }, BACKGROUND_SYNC_MS);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") syncIfStale();
    });
    return () => {
      clearInterval(timer);
      subscription.remove();
    };
  }, [isHome, syncFromBank]);

  /** The refresh button and pull-to-refresh: a visible sync. */
  const syncNow = useCallback(() => syncFromBank(), [syncFromBank]);

  /** After a bank is linked from inside the app: re-read balances, then reload every screen's data. */
  const banksChanged = useCallback(async () => {
    await refresh();
    setSyncVersion((n) => n + 1);
  }, [refresh]);

  switch (gate.step) {
    case "loading":
      return <Loading />;
    case "load-failed":
      return <ErrorState message="Couldn't reach Bankr." onRetry={retry} />;
    case "link-bank":
      // Linking runs the backend's first sync, so re-reading the gate lands on goal setup or home.
      return (
        <LinkBankScreen
          onLinked={() => {
            lastSyncAt.current = Date.now();
            retry();
          }}
        />
      );
    case "set-goal":
      // Goal setup isn't on mobile yet (chat can create goals once home is reachable); finish it on the web.
      return (
        <Screen edges={["top", "bottom"]}>
          <ComingSoon title="Set a goal" detail="Goal setup isn't in the app yet. Finish it on the web, then come back." />
          <Button label="Check again" variant="secondary" onPress={retry} />
          <Button label="Sign out" variant="ghost" onPress={signOut} />
        </Screen>
      );
    case "home":
      return (
        <MoneyProvider value={{ netWorth: gate.netWorth, goals: gate.goals, refresh, banksChanged, syncFromBank: syncNow, isSyncing, syncError, syncVersion }}>
          <PeriodProvider>
            <BankLogosProvider syncVersion={syncVersion}>
              <NotificationsProvider syncVersion={syncVersion}>
                <TransactionFiltersProvider>
                  <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}>
                    <Stack.Screen name="(tabs)" />
                    <Stack.Screen name="notifications" />
                    <Stack.Screen name="recap/[week]" />
                    <Stack.Screen name="money" options={sheet([0.6, 1], colors.bg)} />
                    <Stack.Screen name="history" options={sheet([0.6, 1], colors.bg)} />
                    <Stack.Screen name="source" options={sheet([0.75, 1], colors.bg)} />
                    <Stack.Screen name="filter-date" options={sheet([0.92], colors.bg)} />
                    <Stack.Screen name="filter-category" options={sheet([0.75, 1], colors.bg)} />
                    <Stack.Screen name="filter-account" options={sheet([0.6, 1], colors.bg)} />
                    <Stack.Screen name="filter-direction" options={sheet([0.42], colors.bg)} />
                  </Stack>
                </TransactionFiltersProvider>
              </NotificationsProvider>
            </BankLogosProvider>
          </PeriodProvider>
        </MoneyProvider>
      );
  }
}

/** A native sheet that rests at the given heights (fractions of the screen). */
function sheet(detents: number[], background: string) {
  return {
    presentation: "formSheet" as const,
    sheetAllowedDetents: detents,
    sheetGrabberVisible: true,
    contentStyle: { backgroundColor: background },
  };
}
