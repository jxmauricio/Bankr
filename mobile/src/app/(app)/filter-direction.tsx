import { router } from "expo-router";
import { Pressable, StyleSheet, View } from "react-native";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import type { Direction } from "@/features/transactions/filtering";
import { colors, radius, space } from "@/theme/tokens";
import { Sheet, Text } from "@/ui";

const OPTIONS: { value: Direction; label: string; detail: string }[] = [
  { value: "all", label: "Everything", detail: "Money in and out" },
  { value: "out", label: "Money out", detail: "Spending, bills and transfers out" },
  { value: "in", label: "Money in", detail: "Income, refunds and transfers in" },
];

/** Money in, money out, or both. One tap applies it. */
export default function DirectionFilterSheet() {
  const { filters, update } = useTransactionFilters();
  return (
    <Sheet title="In / Out" scroll={false}>
      <View accessibilityRole="radiogroup" style={styles.list}>
        {OPTIONS.map((o) => {
          const on = filters.direction === o.value;
          return (
            <Pressable
              key={o.value}
              accessibilityRole="radio"
              accessibilityState={{ checked: on }}
              onPress={() => {
                update({ direction: o.value });
                router.back();
              }}
              style={[styles.option, on ? styles.on : styles.off]}
            >
              <Text variant="label">{o.label}</Text>
              <Text variant="meta" tone="faint">
                {o.detail}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  list: { gap: space.sm },
  option: { gap: 2, minHeight: 56, justifyContent: "center", paddingHorizontal: space.md + 2, borderRadius: radius.md, borderWidth: 1 },
  on: { borderColor: colors.accent, backgroundColor: colors.accentWash },
  off: { borderColor: colors.line, backgroundColor: colors.surface },
});
