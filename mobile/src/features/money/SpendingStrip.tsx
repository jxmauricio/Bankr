import { router } from "expo-router";
import { Pressable, StyleSheet, View } from "react-native";
import { VisualsPager } from "@/features/cashflow/VisualsPager";
import type { FlowTarget } from "@/features/cashflow/flow";
import { useMoney } from "@/features/money/MoneyContext";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import { openActivity } from "@/features/transactions/transactionsPage";
import { DEFAULT_FILTERS } from "@/features/transactions/filtering";
import { fetchCashFlow } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { makeStyles, useColors } from "@/theme/theme";
import { Card, Icon, Text } from "@/ui";

/** This month's spending charts on Home. The header opens the full visuals page. */
export function SpendingStrip() {
  const styles = useStyles();
  const colors = useColors();
  const { syncVersion } = useMoney();
  const flow = useResource((token) => fetchCashFlow(token, "this_month"), [syncVersion]);
  const { update } = useTransactionFilters();
  const f = flow.data;

  function openTransactions(target: FlowTarget) {
    update({
      ...DEFAULT_FILTERS,
      date: { kind: "preset", window: "this_month" },
      categories: target.category ? [target.category] : [],
      query: target.query,
    });
    openActivity();
    router.navigate("/transactions");
  }

  return (
    <Card>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Spending"
        onPress={() => router.push("/visuals")}
        style={({ pressed }) => [styles.header, pressed && styles.pressed]}
      >
        <Text variant="sectionTitle" style={styles.flex}>
          Spending
        </Text>
        <Icon name="chevronRight" color={colors.inkFaint} size={20} />
      </Pressable>
      {flow.status === "error" && !f ? (
        <Text tone="soft">Couldn't load spending.</Text>
      ) : !f ? (
        <Text tone="soft">Loading this month's spending…</Text>
      ) : f.spending === 0 && f.income === 0 ? (
        <Text tone="soft">No spending this month yet.</Text>
      ) : (
        <VisualsPager flow={f} onPick={openTransactions} compact />
      )}
    </Card>
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    header: { flexDirection: "row", alignItems: "center" },
    flex: { flex: 1 },
    pressed: { opacity: 0.7 },
  })
);
