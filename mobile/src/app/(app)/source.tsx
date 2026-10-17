import { useLocalSearchParams } from "expo-router";
import { useMemo, useState } from "react";
import { FlatList, StyleSheet, View } from "react-native";
import { fetchQuery, type SourceQuery } from "@/lib/api";
import { describeRowAmount, formatDate, formatMoney } from "@/lib/format";
import { useResource } from "@/lib/useResource";
import { space } from "@/theme/tokens";
import { ErrorState, Initial, ListRow, Loading, Text, TextField } from "@/ui";

/**
 * The transactions behind a chat answer's figure, source, record or chart bar,
 * so the number can be checked here rather than in the bank's app. Ported from
 * the web TransactionSearchModal's query mode.
 */
export default function SourceSheet() {
  const params = useLocalSearchParams<{ q: string; title?: string }>();
  const query = useMemo(() => JSON.parse(params.q) as SourceQuery, [params.q]);
  const { status, data, error, retry } = useResource((token) => fetchQuery(token, query), [params.q]);
  const [search, setSearch] = useState("");

  const group = query.kind === "income" ? "income" : "spending";
  const title =
    params.title || query.category || (query.merchant ? `“${query.merchant}”` : group === "income" ? "Income" : "Spending");
  const q = search.trim().toLowerCase();
  const items = (data?.items ?? []).filter(
    (item) => !q || (item.merchant_name ?? "").toLowerCase().includes(q) || (item.category ?? "").toLowerCase().includes(q)
  );

  if (status === "loading" && !data) return <Loading />;
  if (status === "error" && !data) return <ErrorState message={error} onRetry={retry} />;
  return (
    <FlatList
      data={items}
      keyExtractor={(_, i) => String(i)}
      keyboardDismissMode="on-drag"
      ListHeaderComponent={
        <View style={styles.header}>
          <Text variant="title">{title}</Text>
          {data && (
            <Text variant="caption" tone="faint">
              {data.label} · {data.transaction_count} transaction{data.transaction_count === 1 ? "" : "s"} ·{" "}
              <Text variant="caption">{formatMoney(data.total)}</Text> net
            </Text>
          )}
          <TextField value={search} onChangeText={setSearch} placeholder={`Search ${group} by merchant or category`} />
        </View>
      }
      renderItem={({ item }) => {
        const amount =
          query.kind === "all"
            ? { text: `${item.amount > 0 ? "+" : "−"}${formatMoney(Math.abs(item.amount))}`, isCredit: item.amount > 0 }
            : describeRowAmount(item.amount, group);
        return (
          <ListRow
            leading={<Initial name={item.merchant_name ?? item.category ?? "Transaction"} />}
            title={item.merchant_name ?? item.category ?? "Transaction"}
            subtitle={[
              formatDate(item.date),
              item.category,
              item.is_pending ? "Pending" : null,
              query.kind !== "all" && amount.isCredit ? "Refund" : null,
            ]
              .filter(Boolean)
              .join(" · ")}
            trailing={
              <Text variant="money" tone={amount.isCredit ? "positive" : "default"}>
                {amount.text}
              </Text>
            }
          />
        );
      }}
      ListEmptyComponent={
        <Text tone="soft" align="center" style={styles.empty}>
          {data?.items.length ? "No transactions match your search." : "No transactions in this window."}
        </Text>
      }
    />
  );
}

const styles = StyleSheet.create({
  header: { padding: space.lg, gap: space.sm },
  empty: { padding: space.xl },
});
