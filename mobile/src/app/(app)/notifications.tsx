import { router, type Href } from "expo-router";
import { Pressable, RefreshControl, SectionList, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useState } from "react";
import { useNotifications } from "@/features/notifications/NotificationsContext";
import type { Insight } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import { radius, space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import type { Colors } from "@/theme/tokens";
import { ErrorState, Icon, Loading, PageHeader, SectionHeader, Text, type IconName } from "@/ui";

/** Everything Bankr told you about, newest first: recaps, insights and alerts. */
export default function NotificationsScreen() {
  const styles = useStyles();
  const { insights, unreadCount, loaded, failed, reload, markAllRead } = useNotifications();
  const [refreshing, setRefreshing] = useState(false);

  const sections = [
    { title: "New", data: insights.filter((i) => !i.read) },
    { title: "Earlier", data: insights.filter((i) => i.read) },
  ].filter((s) => s.data.length > 0);

  async function refresh() {
    setRefreshing(true);
    await reload();
    setRefreshing(false);
  }

  return (
    <SafeAreaView style={styles.root} edges={["top"]}>
      <PageHeader
        title="Notifications"
        trailing={
          unreadCount > 0 ? (
            <Pressable accessibilityRole="button" onPress={markAllRead} hitSlop={6} style={({ pressed }) => [styles.markAll, pressed && styles.pressed]}>
              <Text variant="label" tone="accent">
                Mark all read
              </Text>
            </Pressable>
          ) : null
        }
      />
      {!loaded ? (
        <Loading />
      ) : failed && insights.length === 0 ? (
        <ErrorState message="Couldn't load notifications." onRetry={reload} />
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(i) => i.id}
          stickySectionHeadersEnabled={false}
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
          renderSectionHeader={({ section }) => <SectionHeader title={section.title} />}
          renderItem={({ item, index, section }) => (
            <Row insight={item} first={index === 0} last={index === section.data.length - 1} />
          )}
          ListEmptyComponent={
            <Text tone="soft" align="center" style={styles.empty}>
              Nothing yet. Your weekly recap and anything worth a heads-up will show up here.
            </Text>
          }
        />
      )}
    </SafeAreaView>
  );
}

function Row({ insight, first, last }: { insight: Insight; first: boolean; last: boolean }) {
  const styles = useStyles();
  const colors = useColors();
  const { markRead } = useNotifications();
  const look = lookFor(insight.type, colors);
  const target = targetFor(insight);

  return (
    <Pressable
      accessibilityRole={target ? "button" : undefined}
      accessibilityLabel={`${insight.read ? "" : "Unread. "}${insight.message}`}
      onPress={() => {
        markRead(insight);
        if (target) router.push(target);
      }}
      style={({ pressed }) => [
        styles.row,
        first && styles.top,
        last ? styles.bottom : styles.divider,
        pressed && styles.rowPressed,
      ]}
    >
      <View style={[styles.icon, { backgroundColor: look.wash }]}>
        <Icon name={look.icon} color={look.color} size={15} />
      </View>
      <Text variant="body" style={styles.message}>
        {insight.message}
      </Text>
      <View style={styles.meta}>
        <Text variant="meta" tone="faint">
          {formatRelativeTime(insight.created_at)}
        </Text>
        {!insight.read && <View style={styles.dot} />}
      </View>
    </Pressable>
  );
}

function lookFor(type: string, colors: Colors): { icon: IconName; color: string; wash: string } {
  switch (type) {
    case "weekly_recap":
      return { icon: "calendar", color: colors.positive, wash: colors.positiveWash };
    case "budget_overspend":
      return { icon: "warning", color: colors.warn, wash: colors.warnWash };
    case "goal_drift":
      return { icon: "target", color: colors.warn, wash: colors.warnWash };
    case "price_change":
      return { icon: "refresh", color: colors.spend, wash: colors.accentWash };
    default:
      return { icon: "bell", color: colors.accent, wash: colors.accentWash };
  }
}

/** Where a notification leads: the recap it announces, or the tab its subject lives on. */
function targetFor(insight: Insight): Href | null {
  switch (insight.type) {
    case "weekly_recap":
      return insight.subject_id ? `/recap/${insight.subject_id}` : null;
    case "budget_overspend":
    case "goal_drift":
    case "price_change":
      return "/plan";
    case "unusual_transaction":
      return "/transactions";
    default:
      return null;
  }
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.bg },
    content: { paddingBottom: space.xxl, flexGrow: 1 },
    markAll: { height: 44, justifyContent: "center", paddingHorizontal: 6 },
    pressed: { opacity: 0.6 },
    empty: { padding: space.xl },
    row: {
      flexDirection: "row",
      alignItems: "flex-start",
      gap: space.md,
      marginHorizontal: space.lg,
      paddingHorizontal: space.lg,
      paddingVertical: space.md + 2,
      backgroundColor: colors.surface,
      borderColor: colors.line,
      borderLeftWidth: 1,
      borderRightWidth: 1,
    },
    top: { borderTopWidth: 1, borderTopLeftRadius: radius.md + 2, borderTopRightRadius: radius.md + 2 },
    bottom: { borderBottomWidth: 1, borderBottomLeftRadius: radius.md + 2, borderBottomRightRadius: radius.md + 2 },
    divider: { borderBottomWidth: StyleSheet.hairlineWidth },
    rowPressed: { backgroundColor: colors.raised },
    icon: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center" },
    message: { flex: 1 },
    meta: { alignItems: "flex-end", gap: 6 },
    dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.accent },
  })
);
