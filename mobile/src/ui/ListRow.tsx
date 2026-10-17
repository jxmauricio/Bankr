import type { ReactNode } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { colors, space } from "@/theme/tokens";
import { Text } from "./Text";

/** A leading mark, a title/subtitle, and a trailing value, over a hairline. */
export function ListRow({
  title,
  subtitle,
  leading,
  trailing,
  onPress,
}: {
  title: string;
  subtitle?: string | null;
  leading?: ReactNode;
  trailing?: ReactNode;
  onPress?: () => void;
}) {
  return (
    <Pressable onPress={onPress} disabled={!onPress} style={({ pressed }) => [styles.row, pressed && styles.pressed]}>
      {leading}
      <View style={styles.text}>
        <Text numberOfLines={1}>{title}</Text>
        {subtitle ? (
          <Text variant="meta" tone="faint" numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {trailing}
    </Pressable>
  );
}

/** A rounded square with a name's first letter, for rows with no logo. */
export function Initial({ name, size = 36 }: { name: string; size?: number }) {
  return (
    <View style={[styles.initial, { width: size, height: size }]}>
      <Text variant="label" tone="soft">
        {name.charAt(0).toUpperCase()}
      </Text>
    </View>
  );
}

export function SectionHeader({ title }: { title: string }) {
  return (
    <View style={styles.section}>
      <Text variant="meta" tone="faint" style={styles.sectionText}>
        {title}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    minHeight: 60,
    paddingVertical: space.sm,
    paddingHorizontal: space.lg,
    borderBottomColor: colors.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  pressed: { backgroundColor: colors.surface },
  text: { flex: 1, gap: 2 },
  initial: { borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: colors.raised },
  section: { paddingHorizontal: space.lg, paddingTop: space.md + 2, paddingBottom: space.xs, backgroundColor: colors.bg },
  sectionText: { letterSpacing: 0.2 },
});
