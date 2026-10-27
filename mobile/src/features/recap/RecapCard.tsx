import { router } from "expo-router";
import { Pressable, StyleSheet, View } from "react-native";
import { useNotifications } from "@/features/notifications/NotificationsContext";
import { radius, space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Icon, Text } from "@/ui";

/**
 * The latest weekly recap, always at the top of the home screen; it moves
 * on to the new week each Sunday. The dot marks a week not opened yet. The
 * dates are on the recap itself.
 */
export function RecapCard() {
  const styles = useStyles();
  const colors = useColors();
  const { latestRecap } = useNotifications();
  if (!latestRecap) return null;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${latestRecap.read ? "" : "New. "}Your week: ${latestRecap.headline}. ${latestRecap.teaser} Read recap`}
      onPress={() => router.push(`/recap/${latestRecap.week_start}`)}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.icon}>
        <Icon name="calendar" color={colors.positive} size={17} />
      </View>
      <View style={styles.text}>
        <View style={styles.eyebrow}>
          {!latestRecap.read && <View style={styles.dot} />}
          <Text variant="eyebrow" tone="soft">
            Your week
          </Text>
        </View>
        <Text variant="heading">{latestRecap.headline}</Text>
        <Text variant="meta" tone="soft">
          {latestRecap.teaser}
        </Text>
        <View style={styles.link}>
          <Text variant="label" tone="accent">
            Read recap
          </Text>
          <Icon name="chevronRight" color={colors.accent} size={14} />
        </View>
      </View>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    card: {
      flexDirection: "row",
      gap: space.md,
      padding: space.md + 2,
      backgroundColor: colors.surface,
      borderColor: colors.line,
      borderWidth: 1,
      borderRadius: radius.md + 2,
    },
    pressed: { opacity: 0.6 },
    icon: {
      width: 36,
      height: 36,
      borderRadius: 18,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: colors.positiveWash,
    },
    text: { flex: 1, gap: 3 },
    eyebrow: { flexDirection: "row", alignItems: "center", gap: 6 },
    dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.accent },
    link: { flexDirection: "row", alignItems: "center", gap: 3, paddingTop: 3 },
  })
);
