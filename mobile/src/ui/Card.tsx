import type { ReactNode } from "react";
import { StyleSheet, View, type ViewStyle } from "react-native";
import { colors, radius, space } from "@/theme/tokens";

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: radius.md + 2,
    padding: space.lg + 2,
    gap: space.sm,
  },
});
