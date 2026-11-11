import { useEffect, useState } from "react";
import { StyleSheet, Switch, View } from "react-native";
import { fetchNotificationSettings, updateNotificationSettings, type NotificationSettings } from "@/lib/api";
import { useToken } from "@/lib/session";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { SectionHeader, Text } from "@/ui";

type Kind = "daily_briefing" | "weekly_recap";

const KINDS: { key: Kind; label: string; detail: string }[] = [
  { key: "daily_briefing", label: "Daily briefing", detail: "Mornings, when something needs a look" },
  { key: "weekly_recap", label: "Weekly recap", detail: "Sunday evenings" },
];

/** Which pushes this account gets. `embedded` drops the section chrome for a parent card. */
export function PushSettings({ embedded = false }: { embedded?: boolean }) {
  const token = useToken();
  const styles = useStyles();
  const colors = useColors();
  const [prefs, setPrefs] = useState<NotificationSettings | null>(null);

  useEffect(() => {
    fetchNotificationSettings(token).then(setPrefs, () => {});
  }, [token]);

  if (!prefs) return null;

  async function toggle(kind: Kind, on: boolean) {
    if (!prefs) return;
    const before = prefs;
    setPrefs({ ...prefs, [kind]: on });
    try {
      setPrefs(await updateNotificationSettings(token, { [kind]: on }));
    } catch {
      setPrefs(before);
    }
  }

  const rows = KINDS.map(({ key, label, detail }, i) => (
    <View key={key} style={[styles.row, i > 0 && styles.divider, embedded && styles.rowFlush]}>
      <View style={styles.text}>
        <Text variant="label">{label}</Text>
        <Text variant="meta" tone="soft">
          {detail}
        </Text>
      </View>
      <Switch
        accessibilityLabel={label}
        value={prefs[key]}
        onValueChange={(on) => toggle(key, on)}
        trackColor={{ true: colors.accent, false: colors.line }}
      />
    </View>
  ));

  if (embedded) return <View>{rows}</View>;

  return (
    <View style={styles.root}>
      <SectionHeader title="Push notifications" />
      <View style={styles.card}>{rows}</View>
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    root: { marginTop: space.lg },
    card: {
      borderTopWidth: StyleSheet.hairlineWidth,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderColor: colors.line,
      backgroundColor: colors.bg,
    },
    row: { flexDirection: "row", alignItems: "center", gap: space.md, paddingHorizontal: space.lg, paddingVertical: space.md },
    rowFlush: { paddingHorizontal: 0 },
    divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.line },
    text: { flex: 1, gap: 2 },
  })
);
