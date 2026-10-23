import type { ReactNode } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { colors, space } from "@/theme/tokens";
import { Icon, Text } from "@/ui";

// Rows shared by the filter sheets.

export function ClearButton({ onPress }: { onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} hitSlop={10}>
      <Text variant="caption" tone="accent">
        Clear
      </Text>
    </Pressable>
  );
}

/** A checkbox row: box, optional swatch or leading mark, label, count and amount. */
export function CheckRow({
  checked,
  onPress,
  label,
  swatch,
  leading,
  count,
  amount,
}: {
  checked: boolean;
  onPress: () => void;
  label: string;
  swatch?: string;
  leading?: ReactNode;
  count: number;
  amount?: string;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      onPress={onPress}
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
    >
      <View style={[styles.box, checked ? styles.boxOn : styles.boxOff]}>
        {checked && <Icon name="check" size={16} color={colors.onAccent} />}
      </View>
      {swatch && <View style={[styles.swatch, { backgroundColor: swatch }]} />}
      {leading}
      <Text numberOfLines={1} style={styles.flex}>
        {label}
      </Text>
      <Text variant="meta" tone="faint">
        {count}
      </Text>
      {amount && (
        <Text variant="moneySmall" style={styles.amount}>
          {amount}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    minHeight: 52,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  pressed: { opacity: 0.6 },
  box: { width: 22, height: 22, borderRadius: 6, alignItems: "center", justifyContent: "center", borderWidth: 1 },
  boxOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  boxOff: { borderColor: colors.lineStrong },
  swatch: { width: 8, height: 8, borderRadius: 2 },
  flex: { flex: 1 },
  amount: { minWidth: 84, textAlign: "right" },
});
