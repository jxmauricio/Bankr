import type { ReactNode } from "react";
import { Pressable, StyleSheet, View, type ViewStyle } from "react-native";
import { radius, space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Text } from "./Text";

/** Where a row sits in a bordered group of rows, so the group reads as one card. */
export type GroupPosition = "only" | "first" | "middle" | "last";

export function groupPosition(index: number, count: number): GroupPosition {
  if (count === 1) return "only";
  return index === 0 ? "first" : index === count - 1 ? "last" : "middle";
}

/**
 * A leading mark, a title/subtitle, and a trailing value. With `group`, the
 * row is one slice of a bordered card (hairlines between rows); without it,
 * a plain row over a hairline.
 */
export function ListRow({
  title,
  subtitle,
  leading,
  trailing,
  onPress,
  group,
}: {
  title: string;
  subtitle?: string | null;
  leading?: ReactNode;
  trailing?: ReactNode;
  onPress?: () => void;
  group?: GroupPosition;
}) {
  const styles = useStyles();
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [styles.row, group ? groupStyle(styles, group) : styles.plain, pressed && styles.pressed]}
    >
      {leading}
      <View style={styles.text}>
        <Text variant="label" numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text variant="meta" tone="soft" numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {trailing}
    </Pressable>
  );
}

function groupStyle(styles: ReturnType<typeof useStyles>, position: GroupPosition): ViewStyle[] {
  const first = position === "first" || position === "only";
  const last = position === "last" || position === "only";
  return [styles.grouped, first && styles.groupTop, last ? styles.groupBottom : styles.groupDivider].filter(Boolean) as ViewStyle[];
}

/** A circle with a name's first letter, for rows with no logo. */
export function Initial({ name, size = 40 }: { name: string; size?: number }) {
  const styles = useStyles();
  return (
    <View style={[styles.initial, { width: size, height: size, borderRadius: size / 2 }]}>
      <Text variant="heading" tone="soft">
        {name.charAt(0).toUpperCase()}
      </Text>
    </View>
  );
}

/** The uppercase label over a group, with an optional value on the right ("TODAY ... −$90.62"). */
export function SectionHeader({ title, trailing }: { title: string; trailing?: string | null }) {
  const styles = useStyles();
  return (
    <View style={styles.section}>
      <Text variant="section" tone="soft">
        {title}
      </Text>
      {trailing ? (
        <Text variant="moneySmall" tone="soft">
          {trailing}
        </Text>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    row: { flexDirection: "row", alignItems: "center", gap: space.md, minHeight: 64, paddingVertical: space.sm, paddingHorizontal: space.lg },
    plain: { borderBottomColor: colors.line, borderBottomWidth: StyleSheet.hairlineWidth },
    grouped: {
      marginHorizontal: space.lg,
      backgroundColor: colors.surface,
      borderColor: colors.line,
      borderLeftWidth: 1,
      borderRightWidth: 1,
    },
    groupTop: { borderTopWidth: 1, borderTopLeftRadius: radius.md + 2, borderTopRightRadius: radius.md + 2 },
    groupBottom: { borderBottomWidth: 1, borderBottomLeftRadius: radius.md + 2, borderBottomRightRadius: radius.md + 2 },
    groupDivider: { borderBottomWidth: StyleSheet.hairlineWidth },
    pressed: { backgroundColor: colors.raised },
    text: { flex: 1, gap: 2 },
    initial: { alignItems: "center", justifyContent: "center", backgroundColor: colors.raised },
    section: {
      flexDirection: "row",
      justifyContent: "space-between",
      alignItems: "baseline",
      paddingHorizontal: space.lg + space.xs,
      paddingTop: space.lg,
      paddingBottom: space.sm,
      backgroundColor: colors.bg,
    },
  })
);
