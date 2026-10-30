import { router } from "expo-router";
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { useKindColors, sides, whole, type FlowTarget } from "@/features/cashflow/flow";
import { Sankey } from "@/features/cashflow/Sankey";
import { SpendingPaceChart } from "@/features/cashflow/SpendingPaceChart";
import { useMoney } from "@/features/money/MoneyContext";
import { usePeriod } from "@/features/period/PeriodContext";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import { DEFAULT_FILTERS } from "@/features/transactions/filtering";
import { fetchCashFlow, fetchSpendingPace } from "@/lib/api";
import { PERIOD_OPTIONS, periodInfo } from "@/lib/period";
import { useResource } from "@/lib/useResource";
import { useFloatingTabInset } from "@/theme/tabBar";
import { radius, space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Card, ErrorState, Loading, Screen, SegmentedControl, Text } from "@/ui";

/** Where money came from and went for the period, then this month's spending pace. Mirrors the web CashFlowView. */
export default function CashFlowScreen() {
  const styles = useStyles();
  const tabInset = useFloatingTabInset();
  const kindColors = useKindColors();
  const colors = useColors();
  const { period, setPeriod } = usePeriod();
  const { syncFromBank, isSyncing, syncVersion } = useMoney();
  const window = periodInfo(period).window;
  const flow = useResource((token) => fetchCashFlow(token, window), [window, syncVersion]);
  const pace = useResource(fetchSpendingPace, [syncVersion]);

  const { update } = useTransactionFilters();

  /** Transactions, narrowed to what was tapped and this screen's period; other filters reset. */
  function openTransactions(target: FlowTarget) {
    update({
      ...DEFAULT_FILTERS,
      date: { kind: "preset", window },
      categories: target.category ? [target.category] : [],
      query: target.query,
    });
    router.navigate("/transactions");
  }

  const data = flow.data ? sides(flow.data) : null;
  const f = flow.data;
  const empty = f !== null && f.income === 0 && f.spending === 0 && (f.transfer_in ?? 0) === 0 && (f.transfer_out ?? 0) === 0;

  return (
    // The tab bar above owns the top inset.
    <Screen padded={false} edges={[]}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: tabInset + space.md }]}
        refreshControl={<RefreshControl refreshing={isSyncing} onRefresh={syncFromBank} tintColor={colors.accent} />}
      >
        <SegmentedControl label="Period" options={PERIOD_OPTIONS} value={period} onChange={setPeriod} />
        <Text variant="caption" tone="soft" style={styles.intro}>
          Where your money came from and where it went{f ? ` · ${f.label}` : ""}. Tap a category to see its transactions.
        </Text>

        {flow.status === "error" && !f ? (
          <Card>
            <ErrorState message="Couldn't load cash flow." onRetry={flow.retry} />
          </Card>
        ) : !f || !data ? (
          <Card style={styles.placeholder}>
            <Loading />
          </Card>
        ) : empty ? (
          <Card>
            <Text tone="soft" align="center">
              No income, spending, or transfers in {f.label} yet.
            </Text>
          </Card>
        ) : (
          <>
            <Card>
              <Sankey flow={f} {...data} onPick={openTransactions} />
            </Card>
            <Card style={styles.rows}>
              <View style={styles.rowsHeader}>
                <Text variant="section" tone="soft">
                  Where it went
                </Text>
                <Text variant="section" tone="soft">
                  Amount
                </Text>
              </View>
              {data.right.map((c, i) => {
                const maxRow = Math.max(...data.right.map((r) => r.amount), 1);
                return (
                  <Pressable
                    key={`${c.kind}-${c.name}`}
                    disabled={!c.target}
                    onPress={() => c.target && openTransactions(c.target)}
                    style={({ pressed }) => [styles.row, i > 0 && styles.rowLine, pressed && styles.pressed]}
                  >
                    <View style={[styles.swatch, { backgroundColor: kindColors[c.kind] }]} />
                    <Text numberOfLines={1} style={styles.flex}>
                      {c.name}
                    </Text>
                    <View style={styles.bar}>
                      <View style={[styles.barFill, { width: `${(c.amount / maxRow) * 100}%`, backgroundColor: kindColors[c.kind] }]} />
                    </View>
                    <Text variant="money" style={styles.amount}>
                      {whole(c.amount)}
                    </Text>
                    <Text tone="faint" style={styles.chevron}>
                      {c.target ? "›" : ""}
                    </Text>
                  </Pressable>
                );
              })}
            </Card>
          </>
        )}

        {pace.data && <SpendingPaceChart pace={pace.data} />}
      </ScrollView>
    </Screen>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    content: { padding: space.lg, paddingBottom: space.xxl, gap: space.md },
    intro: { paddingHorizontal: space.xs },
    placeholder: { height: 320 },
    rows: { paddingTop: space.md + 2, paddingBottom: space.xs, gap: 0 },
    rowsHeader: { flexDirection: "row", justifyContent: "space-between", paddingBottom: space.xs },
    row: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 44 },
    rowLine: { borderTopColor: colors.line, borderTopWidth: StyleSheet.hairlineWidth },
    pressed: { opacity: 0.6 },
    swatch: { width: 8, height: 8, borderRadius: 2 },
    flex: { flex: 1 },
    bar: { width: 60, height: 4, borderRadius: radius.pill, backgroundColor: colors.line, overflow: "hidden" },
    barFill: { height: 4, borderRadius: radius.pill },
    amount: { minWidth: 72, textAlign: "right" },
    chevron: { width: 10 },
  })
);
