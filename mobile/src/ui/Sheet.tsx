import type { ReactNode } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, space } from "@/theme/tokens";
import { Text } from "./Text";

/** The inside of a bottom sheet: a title row, scrolling content, and an optional fixed footer. */
export function Sheet({
  title,
  trailing,
  footer,
  scroll = true,
  children,
}: {
  title: string;
  trailing?: ReactNode;
  footer?: ReactNode;
  scroll?: boolean;
  children: ReactNode;
}) {
  return (
    <SafeAreaView style={styles.root} edges={["bottom"]}>
      <View style={styles.head}>
        <Text variant="heading" accessibilityRole="header">
          {title}
        </Text>
        {trailing}
      </View>
      {scroll ? (
        <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
          {children}
        </ScrollView>
      ) : (
        <View style={[styles.body, styles.fill]}>{children}</View>
      )}
      {footer && <View style={styles.footer}>{footer}</View>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  head: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: space.lg,
    paddingTop: space.xl,
    paddingBottom: space.sm,
  },
  body: { paddingHorizontal: space.lg, paddingBottom: space.lg, gap: space.md },
  fill: { flex: 1 },
  footer: { paddingHorizontal: space.lg, paddingTop: space.sm, paddingBottom: space.md },
});
