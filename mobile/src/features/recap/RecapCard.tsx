import { router } from "expo-router";
import { Pressable, StyleSheet, View } from "react-native";
import { useNotifications } from "@/features/notifications/NotificationsContext";
import { radius, space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Text } from "@/ui";

/**
 * The latest weekly recap. The only rounded card on Home — short and wide,
 * so it reads as a thing to tap without taking the screen.
 */
export function RecapCard() {
  const styles = useStyles();
  const { latestRecap } = useNotifications();
  if (!latestRecap) return null;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${latestRecap.read ? "" : "New. "}Your week: ${latestRecap.headline}. Read recap`}
      onPress={() => router.push(`/recap/${latestRecap.week_start}`)}
      style={({ pressed }) => [styles.hit, pressed && styles.pressed]}
    >
      <View style={styles.card}>
        {!latestRecap.read && <View style={styles.dot} />}
        <View style={styles.copy}>
          <Text variant="eyebrow" tone="soft">
            Your week
          </Text>
          <Text variant="heading" numberOfLines={1}>
            {latestRecap.headline}
          </Text>
        </View>
        <Text variant="label" tone="accent">
          Read recap →
        </Text>
      </View>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    hit: { marginHorizontal: space.lg, marginTop: space.lg },
    pressed: { opacity: 0.7 },
    card: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.sm,
      minHeight: 56,
      paddingVertical: space.sm + 2,
      paddingHorizontal: space.md,
      borderRadius: radius.md,
      backgroundColor: colors.raised,
    },
    copy: { flex: 1, minWidth: 0, gap: 2 },
    dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.accent },
  })
);
