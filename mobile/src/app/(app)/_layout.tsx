import { Stack } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchGoalProgress,
  fetchNetWorth,
  resyncAccounts,
  type GoalProgressResponse,
  type NetWorthHistory,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { MoneyProvider } from "@/features/money/MoneyContext";
import { BankLogosProvider } from "@/features/bank/BankLogos";
import { LinkBankScreen } from "@/features/bank/LinkBankScreen";
import { PeriodProvider } from "@/features/period/PeriodContext";
import { TransactionFiltersProvider } from "@/features/transactions/FiltersContext";
import { colors } from "@/theme/tokens";
import { Button, ComingSoon, ErrorState, Loading, Screen } from "@/ui";

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
  const { token, signOut } = useSession();
  const [gate, setGate] = useState<Gate>({ step: "loading" });

  // Bumped to run the gate again; the effect below is the only place it runs.
  const [attempt, setAttempt] = useState(0);
  const onRefreshed = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    Promise.all([fetchNetWorth(token), fetchGoalProgress(token)])
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

  /** Same as the web app's refreshFromBank: resync every bank, then re-read. */
  const syncFromBank = useCallback(async () => {
    if (!token || isSyncing) return;
    setIsSyncing(true);
    setSyncError(null);
    try {
      await resyncAccounts(token);
      await refresh();
      setSyncVersion((n) => n + 1);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return signOut();
      setSyncError(err instanceof ApiError ? err.message : "Couldn't refresh from your bank. Try again.");
    } finally {
      setIsSyncing(false);
    }
  }, [token, isSyncing, refresh, signOut]);

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
      return <LinkBankScreen onLinked={retry} />;
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
        <MoneyProvider value={{ netWorth: gate.netWorth, goals: gate.goals, refresh, banksChanged, syncFromBank, isSyncing, syncError, syncVersion }}>
          <PeriodProvider>
            <BankLogosProvider syncVersion={syncVersion}>
              <TransactionFiltersProvider>
                <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}>
                  <Stack.Screen name="(tabs)" />
                  <Stack.Screen name="money" options={sheet([0.6, 1])} />
                  <Stack.Screen name="history" options={sheet([0.6, 1])} />
                  <Stack.Screen name="source" options={sheet([0.75, 1])} />
                  <Stack.Screen name="filter-date" options={sheet([0.92])} />
                  <Stack.Screen name="filter-category" options={sheet([0.75, 1])} />
                  <Stack.Screen name="filter-account" options={sheet([0.6, 1])} />
                  <Stack.Screen name="filter-direction" options={sheet([0.42])} />
                </Stack>
              </TransactionFiltersProvider>
            </BankLogosProvider>
          </PeriodProvider>
        </MoneyProvider>
      );
  }
}

/** A native sheet that rests at the given heights (fractions of the screen). */
function sheet(detents: number[]) {
  return {
    presentation: "formSheet" as const,
    sheetAllowedDetents: detents,
    sheetGrabberVisible: true,
    contentStyle: { backgroundColor: colors.bg },
  };
}
