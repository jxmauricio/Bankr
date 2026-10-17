import { Pressable, StyleSheet, View } from "react-native";
import { colors, radius, space } from "@/theme/tokens";
import { IconButton, Text } from "@/ui";
import { iso } from "./filtering";

const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];

/**
 * One month of days with a start–end range drawn on it: the ends filled in the
 * accent, the days between washed. Future days can't be picked (there's no
 * future spending). The parent owns the month and what a tap means.
 */
export function RangeCalendar({
  month,
  onMonthChange,
  start,
  end,
  today,
  onPick,
}: {
  /** Any day in the month to show. */
  month: Date;
  onMonthChange: (month: Date) => void;
  start: string | null;
  end: string | null;
  today: string;
  onPick: (day: string) => void;
}) {
  const y = month.getFullYear();
  const m = month.getMonth();
  const lead = new Date(y, m, 1).getDay();
  const daysIn = new Date(y, m + 1, 0).getDate();
  const lo = start;
  const hi = end ?? start;
  const atLatest = iso(new Date(y, m + 1, 1)) > today;

  const cells: (string | null)[] = [...Array(lead).fill(null)];
  for (let d = 1; d <= daysIn; d++) cells.push(iso(new Date(y, m, d)));
  while (cells.length % 7) cells.push(null);

  return (
    <View style={styles.box}>
      <View style={styles.head}>
        <IconButton icon="chevronLeft" label="Previous month" onPress={() => onMonthChange(new Date(y, m - 1, 1))} />
        <Text variant="label">{month.toLocaleDateString("en-US", { month: "long", year: "numeric" })}</Text>
        <IconButton
          icon="chevronRight"
          label="Next month"
          onPress={() => onMonthChange(new Date(y, m + 1, 1))}
          disabled={atLatest}
        />
      </View>
      <View style={styles.row} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
        {WEEKDAYS.map((w, i) => (
          <Text key={i} variant="meta" tone="faint" align="center" style={styles.cell}>
            {w}
          </Text>
        ))}
      </View>
      <View style={styles.grid}>
        {cells.map((day, i) => {
          if (!day) return <View key={`blank-${i}`} style={styles.cell} />;
          const future = day > today;
          const edge = day === lo || day === hi;
          const inside = lo !== null && hi !== null && day > lo && day < hi;
          return (
            <Pressable
              key={day}
              disabled={future}
              onPress={() => onPick(day)}
              accessibilityRole="button"
              accessibilityLabel={new Date(y, m, Number(day.slice(8))).toLocaleDateString("en-US", {
                weekday: "long",
                month: "long",
                day: "numeric",
              })}
              accessibilityState={{ selected: edge || inside, disabled: future }}
              style={styles.cell}
            >
              <View style={[styles.day, inside && styles.inside, edge && styles.edge]}>
                <Text variant="money" tone={edge ? "onAccent" : future ? "faint" : "default"} style={future && styles.future}>
                  {Number(day.slice(8))}
                </Text>
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
  },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  row: { flexDirection: "row" },
  grid: { flexDirection: "row", flexWrap: "wrap", rowGap: 4 },
  cell: { width: `${100 / 7}%`, alignItems: "center" },
  day: { width: "100%", height: 40, alignItems: "center", justifyContent: "center", borderRadius: 10 },
  inside: { backgroundColor: colors.accentWash },
  edge: { backgroundColor: colors.accent },
  future: { opacity: 0.35 },
});
