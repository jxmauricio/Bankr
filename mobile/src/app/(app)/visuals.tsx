import { router } from "expo-router";
import { RefreshControl, ScrollView, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { VisualsBoard } from "@/features/cashflow/VisualsBoard";
import { useMoney } from "@/features/money/MoneyContext";
import { usePeriod } from "@/features/period/PeriodContext";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import { openActivity } from "@/features/transactions/transactionsPage";
import { DEFAULT_FILTERS } from "@/features/transactions/filtering";
import type { FlowTarget } from "@/features/cashflow/flow";
import { fetchCashFlow, fetchSpendingPace } from "@/lib/api";
import { periodInfo } from "@/lib/period";
import { useResource } from "@/lib/useResource";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { PageHeader } from "@/ui";

/** Flow, pie, and bars for the period. Opened from Home spending. */
export default function VisualsScreen() {
  const styles = useStyles();
  const colors = useColors();
  const { period } = usePeriod();
  const { syncFromBank, isSyncing, syncVersion } = useMoney();
  const window = periodInfo(period).window;
  const flow = useResource((token) => fetchCashFlow(token, window), [window, syncVersion]);
  const pace = useResource(fetchSpendingPace, [syncVersion]);
  const { update } = useTransactionFilters();

  function openTransactions(target: FlowTarget) {
    update({
      ...DEFAULT_FILTERS,
      date: { kind: "preset", window },
      categories: target.category ? [target.category] : [],
      query: target.query,
    });
    openActivity();
    router.navigate("/transactions");
  }

  return (
    <SafeAreaView style={styles.root} edges={["top"]}>
      <PageHeader title="Spending" />
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isSyncing} onRefresh={syncFromBank} tintColor={colors.accent} />}
      >
        <VisualsBoard flow={flow} pace={pace} onRetry={flow.retry} onPick={openTransactions} />
      </ScrollView>
    </SafeAreaView>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.bg },
    content: { paddingBottom: space.xxl },
  })
);
