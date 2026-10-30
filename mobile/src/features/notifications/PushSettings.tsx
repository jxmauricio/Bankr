import { useEffect, useState } from "react";
import { StyleSheet, Switch, View } from "react-native";
import { fetchNotificationSettings, updateNotificationSettings, type NotificationSettings } from "@/lib/api";
import { useToken } from "@/lib/session";
import { radius, space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { SectionHeader, Text } from "@/ui";

type Kind = "daily_briefing" | "weekly_recap";

const KINDS: { key: Kind; label: string; detail: string }[] = [
  { key: "daily_briefing", label: "Daily briefing", detail: "Mornings, when something needs a look" },
  { key: "weekly_recap", label: "Weekly recap", detail: "Sunday evenings" },
];

/** Which pushes this account gets, under the notifications list. */
export function PushSettings() {
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

  return (
    <View style={styles.root}>
      <SectionHeader title="Push notifications" />
      <View style={styles.card}>
        {KINDS.map(({ key, label, detail }, i) => (
          <View key={key} style={[styles.row, i > 0 && styles.divider]}>
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
        ))}
      </View>
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    root: { marginTop: space.lg },
    card: {
      marginHorizontal: space.lg,
      borderWidth: 1,
      borderColor: colors.line,
      borderRadius: radius.md + 2,
      backgroundColor: colors.surface,
    },
    row: { flexDirection: "row", alignItems: "center", gap: space.md, paddingHorizontal: space.lg, paddingVertical: space.md },
    divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.line },
    text: { flex: 1, gap: 2 },
  })
);
