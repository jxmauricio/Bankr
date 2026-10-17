import { router } from "expo-router";
import { Pressable, StyleSheet } from "react-native";
import { formatMoney } from "@/lib/format";
import { colors, radius, space } from "@/theme/tokens";
import { Text } from "@/ui";
import { useMoney } from "./MoneyContext";

/** Net worth at a glance in the header; tapping it opens the money sheet. */
export function MoneyPill() {
  const { netWorth } = useMoney();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Your money"
      onPress={() => router.push("/money")}
      style={({ pressed }) => [styles.pill, pressed && styles.pressed]}
    >
      <Text variant="caption" tone="soft">
        Net worth
      </Text>
      <Text variant="money">{netWorth.current === null ? "—" : formatMoney(netWorth.current)}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: space.sm,
    minHeight: 44,
    paddingHorizontal: space.md + 2,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderWidth: 1,
  },
  pressed: { borderColor: colors.accent },
});
