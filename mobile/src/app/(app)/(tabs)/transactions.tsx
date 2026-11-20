import { router } from "expo-router";
import { useMemo } from "react";
import { RefreshControl, SectionList, StyleSheet, View } from "react-native";
import { ScrollView } from "react-native-gesture-handler";
import { useMoney } from "@/features/money/MoneyContext";
import { RecurringList } from "@/features/transactions/RecurringList";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import { useTransactionsPage } from "@/features/transactions/transactionsPage";
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
import { useFloatingTabInset } from "@/theme/tabBar";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import {
  Button,
  Card,
  ErrorState,
  FilterChip,
  groupPosition,
  ListRow,
  MerchantMark,
  Loading,
  ResetChip,
  Screen,
  SearchField,
  SectionHeader,
  SegmentedControl,
  Text,
  ToggleChip,
  type GroupPosition,
} from "@/ui";

/**
 * Recurring payments, or the line-by-line list (search, chips, rows by day).
 */
export default function TransactionsScreen() {
  const styles = useStyles();
  const [page, setPage] = useTransactionsPage();

  return (
    // The tab bar above owns the top inset.
    <Screen padded={false} edges={[]}>
      <SegmentedControl
        label="Transactions view"
        value={page}
        onChange={setPage}
        options={[
          { value: "recurring", label: "Recurring" },
          { value: "activity", label: "Transactions" },
        ]}
      />
      <View style={styles.page}>{page === "recurring" ? <RecurringList /> : <Activity />}</View>
    </Screen>
  );
}

function Activity() {
  const styles = useStyles();
  const colors = useColors();
  const tabInset = useFloatingTabInset();
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
  const reset = () => update(DEFAULT_FILTERS);

  function toggleQuick(id: QuickId) {
    update({ quick: filters.quick.includes(id) ? filters.quick.filter((q) => q !== id) : [...filters.quick, id] });
  }

  return (
    <View style={styles.page}>
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
        {filters.merchants.length > 0 ? (
          <FilterChip
            label={filters.merchants.length === 1 ? filters.merchants[0] : `${filters.merchants.length} vendors`}
            active
            onPress={() => update({ merchants: [] })}
            onClear={() => update({ merchants: [] })}
          />
        ) : null}
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
          contentContainerStyle={[styles.listContent, { paddingBottom: tabInset + space.md }]}
          renderSectionHeader={({ section }) => (
            <SectionHeader title={section.title} trailing={section.out > 0 ? `−${formatMoney(section.out)}` : null} />
          )}
          renderItem={({ item, index, section }) => (
            <TransactionItem transaction={item} group={groupPosition(index, section.data.length)} />
          )}
          ListHeaderComponent={
            data ? (
              <Card style={styles.summary}>
                <View accessible accessibilityLabel={summaryLabel(totals)} style={styles.totals}>
                  <View style={styles.total}>
                    <Text variant="moneyLarge" style={styles.totalFigure}>
                      {formatMoney(totals.out)}
                    </Text>
                    <Text variant="caption" tone="soft">
                      spent
                    </Text>
                  </View>
                  <View style={styles.divider} />
                  <View style={[styles.total, styles.totalEnd]}>
                    <Text variant="moneyLarge" tone="positive" style={styles.totalFigure}>
                      {formatMoney(totals.in)}
                    </Text>
                    <Text variant="caption" tone="soft">
                      earned
                    </Text>
                  </View>
                </View>
                <Text variant="meta" tone="soft">
                  {totals.count} {totals.count === 1 ? "transaction" : "transactions"} · {dateLabel(filters.date)}
                </Text>
              </Card>
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
    </View>
  );
}

function summaryLabel(t: { count: number; out: number; in: number }): string {
  return `${t.count} transactions, ${formatMoney(t.out)} out, ${formatMoney(t.in)} in`;
}

function TransactionItem({ transaction, group }: { transaction: TransactionRow; group: GroupPosition }) {
  const amount = signedAmount(transaction.amount);
  const subtitle = [topCategory(transaction), transaction.is_pending ? "Pending" : null].filter(Boolean).join(" · ");
  return (
    <ListRow
      group={group}
      leading={<MerchantMark name={merchantOf(transaction)} />}
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

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    page: { flex: 1 },
    search: { paddingHorizontal: space.lg, paddingTop: space.md + 2 },
    // Horizontal rows keep their height; the list below takes what's left.
    row: { flexGrow: 0, flexShrink: 0 },
    chips: { gap: space.sm, paddingHorizontal: space.lg, paddingTop: space.sm + 2, paddingBottom: space.sm + 2 },
    quick: { gap: 6, paddingHorizontal: space.lg, paddingBottom: space.sm + 2 },
    listContent: { paddingBottom: space.xxl },
    summary: { gap: space.md },
    totals: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    total: { flex: 1, gap: 2 },
    totalEnd: { alignItems: "flex-end" },
    totalFigure: { fontSize: 24, letterSpacing: -0.8 },
    divider: { width: 1, alignSelf: "stretch", backgroundColor: colors.line, marginHorizontal: space.md },
    note: { padding: space.lg },
    empty: { padding: space.xl, gap: space.md, alignItems: "center" },
  })
);
