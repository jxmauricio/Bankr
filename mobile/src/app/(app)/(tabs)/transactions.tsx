import { router } from "expo-router";
import { useMemo } from "react";
import { RefreshControl, ScrollView, SectionList, StyleSheet, View } from "react-native";
import { AppHeader } from "@/features/money/AppHeader";
import { useMoney } from "@/features/money/MoneyContext";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import {
  applyFilters,
  dateLabel,
  DEFAULT_FILTERS,
  groupByDay,
  isFiltered,
  QUICK_FILTERS,
  summarize,
  type QuickId,
} from "@/features/transactions/filtering";
import type { TransactionRow } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { merchantOf, signedAmount, topCategory } from "@/lib/transactions";
import { colors, radius, space } from "@/theme/tokens";
import { Button, ErrorState, FilterChip, Initial, ListRow, Loading, ResetChip, Screen, SearchField, Text, ToggleChip } from "@/ui";

/**
 * Search, a row of filter chips (each opens its sheet), one-tap quick filters,
 * a summary of what's shown, then the rows by day. Ported from the
 * "Transactions · filter chips" board in the Bankr Mobile design.
 */
export default function TransactionsScreen() {
  const { syncFromBank, isSyncing } = useMoney();
  const { filters, update, list } = useTransactionFilters();
  const { status, data, error, retry } = list;

  const shown = useMemo(() => applyFilters(data?.transactions ?? [], filters), [data, filters]);
  const sections = useMemo(() => groupByDay(shown), [shown]);
  const totals = summarize(shown);

  const categoryLabel =
    filters.categories.length === 0
      ? "Category"
      : filters.categories.length === 1
        ? filters.categories[0]
        : `${filters.categories.length} categories`;
  const accountLabel =
    filters.accountIds.length === 0 ? "Account" : `${filters.accountIds.length} account${filters.accountIds.length === 1 ? "" : "s"}`;
  const directionLabel = filters.direction === "all" ? "In / Out" : filters.direction === "in" ? "Money in" : "Money out";

  const filtered = isFiltered(filters);
  /** Back to this month, every transaction, empty search. */
  const reset = () => update(DEFAULT_FILTERS);

  function toggleQuick(id: QuickId) {
    update({ quick: filters.quick.includes(id) ? filters.quick.filter((q) => q !== id) : [...filters.quick, id] });
  }

  return (
    <Screen padded={false}>
      <AppHeader />
      <View style={styles.search}>
        <SearchField
          value={filters.query}
          onChangeText={(query) => update({ query })}
          placeholder="Merchant, category or amount"
          accessibilityLabel="Search transactions"
        />
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.row} contentContainerStyle={styles.chips}>
        {/* First in the row, so it's visible without scrolling whenever there's something to undo. */}
        {filtered && <ResetChip onPress={reset} />}
        <FilterChip label={dateLabel(filters.date)} icon="calendar" active onPress={() => router.push("/filter-date")} />
        <FilterChip
          label={categoryLabel}
          active={filters.categories.length > 0}
          onPress={() => router.push("/filter-category")}
          onClear={() => update({ categories: [] })}
        />
        <FilterChip
          label={accountLabel}
          active={filters.accountIds.length > 0}
          onPress={() => router.push("/filter-account")}
          onClear={() => update({ accountIds: [] })}
        />
        <FilterChip
          label={directionLabel}
          active={filters.direction !== "all"}
          onPress={() => router.push("/filter-direction")}
          onClear={() => update({ direction: "all" })}
        />
      </ScrollView>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.row} contentContainerStyle={styles.quick}>
        {QUICK_FILTERS.map((q) => (
          <ToggleChip key={q.id} label={q.label} on={filters.quick.includes(q.id)} onToggle={() => toggleQuick(q.id)} />
        ))}
      </ScrollView>

      {status === "loading" && !data ? (
        <Loading />
      ) : status === "error" && !data ? (
        <ErrorState message={error} onRetry={retry} />
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(t) => t.id}
          stickySectionHeadersEnabled
          keyboardDismissMode="on-drag"
          refreshControl={<RefreshControl refreshing={isSyncing} onRefresh={syncFromBank} tintColor={colors.accent} />}
          renderSectionHeader={({ section }) => (
            <View style={styles.dayHeader}>
              <Text variant="meta" tone="faint">
                {section.title}
              </Text>
              {section.out > 0 && (
                <Text variant="moneySmall" tone="faint">
                  −{formatMoney(section.out)}
                </Text>
              )}
            </View>
          )}
          renderItem={({ item }) => <TransactionItem transaction={item} />}
          ListHeaderComponent={
            data ? (
              <View style={styles.summary} accessible accessibilityLabel={summaryLabel(totals)}>
                <Text variant="caption" tone="soft">
                  {totals.count} {totals.count === 1 ? "transaction" : "transactions"}
                </Text>
                <View style={styles.totals}>
                  <Text variant="moneySmall">
                    {formatMoney(totals.out)}{" "}
                    <Text variant="caption" tone="faint">
                      out
                    </Text>
                  </Text>
                  <Text variant="moneySmall" tone="positive">
                    {formatMoney(totals.in)}{" "}
                    <Text variant="caption" tone="faint">
                      in
                    </Text>
                  </Text>
                </View>
              </View>
            ) : null
          }
          ListFooterComponent={
            data?.truncated ? (
              <Text variant="meta" tone="faint" align="center" style={styles.note}>
                Showing the newest {data.transactions.length.toLocaleString("en-US")}. Pick a shorter date range to see the rest.
              </Text>
            ) : null
          }
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text tone="soft" align="center">
                {data?.transactions.length ? "No transactions match these filters." : "No transactions in these dates."}
              </Text>
              {filtered && <Button label="Reset filters" variant="secondary" onPress={reset} />}
            </View>
          }
        />
      )}
    </Screen>
  );
}

function summaryLabel(t: { count: number; out: number; in: number }): string {
  return `${t.count} transactions, ${formatMoney(t.out)} out, ${formatMoney(t.in)} in`;
}

function TransactionItem({ transaction }: { transaction: TransactionRow }) {
  const amount = signedAmount(transaction.amount);
  const subtitle = [topCategory(transaction), transaction.is_pending ? "Pending" : null].filter(Boolean).join(" · ");
  return (
    <ListRow
      leading={<Initial name={merchantOf(transaction)} />}
      title={merchantOf(transaction)}
      subtitle={subtitle}
      trailing={
        <Text variant="money" tone={amount.tone}>
          {amount.text}
        </Text>
      }
    />
  );
}

const styles = StyleSheet.create({
  search: { paddingHorizontal: space.lg, paddingTop: space.md + 2 },
  // Horizontal rows keep their height; the list below takes what's left.
  row: { flexGrow: 0, flexShrink: 0 },
  chips: { gap: space.sm, paddingHorizontal: space.lg, paddingTop: space.sm + 2, paddingBottom: space.sm + 2 },
  quick: { gap: 6, paddingHorizontal: space.lg, paddingBottom: space.sm + 2 },
  summary: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: space.sm,
    marginHorizontal: space.lg,
    marginBottom: space.xs,
    paddingHorizontal: space.md + 2,
    paddingVertical: space.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  totals: { flexDirection: "row", gap: space.md },
  dayHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: space.lg,
    paddingTop: space.md + 2,
    paddingBottom: space.xs,
    backgroundColor: colors.bg,
  },
  note: { padding: space.lg },
  empty: { padding: space.xl, gap: space.md, alignItems: "center" },
});
