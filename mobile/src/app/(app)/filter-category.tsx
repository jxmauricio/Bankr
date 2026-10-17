import { router } from "expo-router";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import { categoryOptions, dateLabel } from "@/features/transactions/filtering";
import { colorForCategory, hasCategoryColor } from "@/lib/chartColors";
import { formatMoney } from "@/lib/format";
import { CheckRow, ClearButton } from "@/features/transactions/FilterRows";
import { colors, space } from "@/theme/tokens";
import { Button, SearchField, Sheet, Text } from "@/ui";

/** Pick any number of categories; each shows its count and spend for the chosen dates. */
export default function CategoryFilterSheet() {
  const { filters, update, list } = useTransactionFilters();
  const [picked, setPicked] = useState<string[]>(filters.categories);
  const [find, setFind] = useState("");

  const q = find.trim().toLowerCase();
  const options = categoryOptions(list.data?.transactions ?? []).filter((c) => !q || c.name.toLowerCase().includes(q));
  const toggle = (name: string) => setPicked((p) => (p.includes(name) ? p.filter((x) => x !== name) : [...p, name]));

  return (
    <Sheet
      title="Category"
      trailing={<ClearButton onPress={() => setPicked([])} />}
      footer={
        <Button
          label={picked.length ? `Show ${picked.length} ${picked.length === 1 ? "category" : "categories"}` : "Show all categories"}
          onPress={() => {
            update({ categories: picked });
            router.back();
          }}
        />
      }
    >
      <SearchField value={find} onChangeText={setFind} placeholder="Find a category" />
      <Text variant="meta" tone="faint">
        {dateLabel(filters.date)} · sorted by amount
      </Text>
      <View accessibilityRole="list">
        {options.map((c) => (
          <CheckRow
            key={c.name}
            checked={picked.includes(c.name)}
            onPress={() => toggle(c.name)}
            label={c.name}
            swatch={hasCategoryColor(c.name) ? colorForCategory(c.name) : colors.inkFaint}
            count={c.count}
            amount={formatMoney(c.amount)}
          />
        ))}
        {options.length === 0 && (
          <Text tone="soft" align="center" style={styles.empty}>
            {q ? "No category by that name." : "No transactions in these dates."}
          </Text>
        )}
      </View>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  empty: { padding: space.xl },
});
