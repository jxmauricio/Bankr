import type { ReactNode } from "react";
import { ScrollView, StyleSheet, View, type ViewStyle } from "react-native";
import { SafeAreaView, type Edge } from "react-native-safe-area-context";
import { colors, space } from "@/theme/tokens";

/**
 * The page every screen sits on. `scroll` wraps the content in a ScrollView;
 * leave it off for screens that manage their own list (FlatList) or keyboard.
 */
export function Screen({
  children,
  scroll = false,
  padded = true,
  // Bottom too: on a tab screen that inset includes the tab bar, which floats over content.
  edges = ["top", "bottom"],
  contentStyle,
}: {
  children: ReactNode;
  scroll?: boolean;
  padded?: boolean;
  edges?: Edge[];
  contentStyle?: ViewStyle;
}) {
  const inner = [padded && styles.padded, contentStyle];
  return (
    <SafeAreaView style={styles.root} edges={edges}>
      {scroll ? (
        <ScrollView contentContainerStyle={inner} keyboardShouldPersistTaps="handled">
          {children}
        </ScrollView>
      ) : (
        <View style={[styles.fill, ...inner]}>{children}</View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  fill: { flex: 1 },
  padded: { padding: space.lg, gap: space.md },
});
