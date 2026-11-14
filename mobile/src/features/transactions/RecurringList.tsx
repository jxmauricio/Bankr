import { router } from "expo-router";
import { useMemo } from "react";
import { RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { useMoney } from "@/features/money/MoneyContext";
import { useRecurringTick } from "@/features/transactions/transactionsPage";
import { fetchRecurring, type RecurringSeries } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { useResource } from "@/lib/useResource";
import { useFloatingTabInset } from "@/theme/tabBar";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Card, ErrorState, Icon, Initial, ListRow, Loading, Text } from "@/ui";

const CADENCE: Record<string, string> = {
  weekly: "Weekly",
  biweekly: "Every 2 weeks",
  monthly: "Monthly",
  quarterly: "Quarterly",
  yearly: "Yearly",
};

/** Subscriptions and bills, highest monthly cost first. Tap a row to fix it. */
export function RecurringList() {
  const styles = useStyles();
  const colors = useColors();
  const tabInset = useFloatingTabInset();
  const { syncFromBank, isSyncing, syncVersion } = useMoney();
  const tick = useRecurringTick();
  const list = useResource(fetchRecurring, [syncVersion, tick]);
  const rows = useMemo(() => {
    const series = (list.data?.series ?? []).filter((s) => s.kind !== "income");
    return [...series].sort((a, b) => b.monthly_amount - a.monthly_amount || b.last_amount - a.last_amount || a.name.localeCompare(b.name));
  }, [list.data]);
  const monthly = rows.reduce((sum, s) => sum + s.monthly_amount, 0);

  if (list.status === "error" && !list.data) {
    return <ErrorState message={list.error} onRetry={list.retry} />;
  }
  if (!list.data) {
    return <Loading />;
  }

  return (
    <ScrollView
      style={styles.flex}
      contentContainerStyle={[styles.content, { paddingBottom: tabInset + space.md }]}
      refreshControl={<RefreshControl refreshing={isSyncing} onRefresh={syncFromBank} tintColor={colors.accent} />}
      keyboardDismissMode="on-drag"
    >
      <Card>
        <Text variant="moneyLarge">{formatMoney(monthly)}</Text>
        <Text variant="caption" tone="soft">
          per month
        </Text>
      </Card>
      {rows.length === 0 ? (
        <Text tone="soft">No recurring payments yet.</Text>
      ) : (
        rows.map((s) => (
          <RecurringRow key={s.id} series={s} onPress={() => router.push({ pathname: "/recurring-edit", params: { id: s.id } })} />
        ))
      )}
    </ScrollView>
  );
}

function RecurringRow({ series, onPress }: { series: RecurringSeries; onPress: () => void }) {
  const styles = useStyles();
  const colors = useColors();
  const next = formatDate(series.next_expected_date);
  const bits = [`Next ${next}`, CADENCE[series.cadence] ?? series.cadence];
  if (series.status === "suggested") bits.push("Suggested");
  return (
    <ListRow
      onPress={onPress}
      leading={<Initial name={series.name} />}
      title={series.name}
      subtitle={bits.join(" · ")}
      trailing={
        <View style={styles.trailing}>
          <Text variant="money">{formatMoney(series.last_amount)}</Text>
          <Icon name="pencil" color={colors.inkFaint} size={16} />
        </View>
      }
    />
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    flex: { flex: 1 },
    content: { paddingTop: space.sm },
    trailing: { flexDirection: "row", alignItems: "center", gap: space.sm },
  })
);
