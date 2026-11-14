import { Pressable, StyleSheet, View } from "react-native";
import { colorForCategory, hasCategoryColor } from "@/lib/chartColors";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Text } from "@/ui";
import { whole } from "./flow";
import type { Slice } from "./SpendingPie";

/** Horizontal bars of spending categories, biggest first. */
export function SpendingBars({ slices, onPick }: { slices: Slice[]; onPick?: (name: string) => void }) {
  const styles = useStyles();
  const colors = useColors();
  const max = Math.max(...slices.map((s) => s.amount), 1);

  return (
    <View style={styles.list}>
      {slices.map((s) => {
        const color = hasCategoryColor(s.name) ? colorForCategory(s.name) : colors.spend;
        const row = (
          <View style={styles.row}>
            <View style={styles.meta}>
              <Text numberOfLines={1} style={styles.flex}>
                {s.name}
              </Text>
              <Text variant="money">{whole(s.amount)}</Text>
            </View>
            <View style={styles.track}>
              <View style={[styles.fill, { width: `${(s.amount / max) * 100}%`, backgroundColor: color }]} />
            </View>
          </View>
        );
        if (!onPick) return <View key={s.name}>{row}</View>;
        return (
          <Pressable key={s.name} accessibilityRole="button" onPress={() => onPick(s.name)} style={({ pressed }) => pressed && styles.pressed}>
            {row}
          </Pressable>
        );
      })}
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    list: { gap: space.md },
    row: { gap: 6 },
    meta: { flexDirection: "row", alignItems: "baseline", gap: space.sm },
    flex: { flex: 1, minWidth: 0 },
    track: { height: 10, borderRadius: 5, backgroundColor: colors.line, overflow: "hidden" },
    fill: { height: "100%", borderRadius: 5 },
    pressed: { opacity: 0.6 },
  })
);
