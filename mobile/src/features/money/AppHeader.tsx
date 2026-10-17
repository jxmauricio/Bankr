import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import { colors, space } from "@/theme/tokens";
import { MoneyPill } from "./MoneyPill";

/** The bar every tab shares: an optional leading action, the money pill, an optional trailing action. */
export function AppHeader({ leading, trailing }: { leading?: ReactNode; trailing?: ReactNode }) {
  return (
    <View style={styles.bar}>
      {leading}
      <View style={styles.pill}>
        <MoneyPill />
      </View>
      {trailing}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomColor: colors.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  pill: { flex: 1 },
});
