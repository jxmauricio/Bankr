import { router } from "expo-router";
import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import { space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { IconButton } from "./IconButton";
import { Text } from "./Text";

/**
 * The bar over a screen pushed on top of the tabs: back on the left, the
 * title centered, and an optional action on the right. Both sides are the
 * same width so the title stays centered.
 */
export function PageHeader({ title, trailing }: { title: string; trailing?: ReactNode }) {
  const styles = useStyles();
  return (
    <View style={styles.bar}>
      <View style={styles.side}>
        {/* Opened from a link (a tapped notification) there's no screen behind it: go home instead. */}
        <IconButton
          icon="chevronLeft"
          label="Back"
          variant="plain"
          onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))}
        />
      </View>
      <Text variant="heading" accessibilityRole="header" numberOfLines={1} style={styles.title}>
        {title}
      </Text>
      <View style={[styles.side, styles.trailing]}>{trailing}</View>
    </View>
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    bar: { flexDirection: "row", alignItems: "center", paddingHorizontal: space.sm + 2, minHeight: 52 },
    side: { width: 110, flexDirection: "row" },
    trailing: { justifyContent: "flex-end" },
    title: { flex: 1, textAlign: "center" },
  })
);
