import { Pressable, StyleSheet, View } from "react-native";
import Svg, { Path } from "react-native-svg";
import { colorForCategory, hasCategoryColor } from "@/lib/chartColors";
import { makeStyles, useColors } from "@/theme/theme";
import { space } from "@/theme/tokens";
import { Text } from "@/ui";
import { whole } from "./flow";

export interface Slice {
  name: string;
  amount: number;
}

function polar(cx: number, cy: number, r: number, angle: number) {
  return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
}

function wedge(cx: number, cy: number, r: number, from: number, to: number) {
  const start = polar(cx, cy, r, from);
  const end = polar(cx, cy, r, to);
  const large = to - from > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${start.x} ${start.y} A ${r} ${r} 0 ${large} 1 ${end.x} ${end.y} Z`;
}

function sliceColor(name: string, fallback: string): string {
  return hasCategoryColor(name) ? colorForCategory(name) : fallback;
}

/** Pie of spending categories. Home uses names under the chart; the expanded
 * view passes `amounts` so each slice also shows what it cost. */
export function SpendingPie({
  slices,
  size = 140,
  otherColor,
  onPick,
  legend = true,
  amounts = legend !== "bottom",
}: {
  slices: Slice[];
  size?: number;
  otherColor: string;
  onPick?: (name: string) => void;
  legend?: boolean | "bottom";
  amounts?: boolean;
}) {
  const styles = useStyles();
  const colors = useColors();
  const total = slices.reduce((s, c) => s + c.amount, 0);
  const r = size / 2;
  let angle = -Math.PI / 2;
  const below = legend === "bottom";

  const chart = (
    <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {total <= 0 ? (
        <Path d={wedge(r, r, r - 1, 0, Math.PI * 2 - 0.001)} fill={colors.line} />
      ) : (
        slices.map((s) => {
          const sweep = (s.amount / total) * Math.PI * 2;
          const from = angle;
          angle += sweep;
          return (
            <Path
              key={s.name}
              d={wedge(r, r, r - 1, from, from + Math.max(sweep, 0.02))}
              fill={sliceColor(s.name, otherColor)}
              stroke={colors.surface}
              strokeWidth={2}
            />
          );
        })
      )}
    </Svg>
  );

  const items = slices.map((s) => {
    const row = below ? (
      <View style={styles.tag}>
        <View style={[styles.swatch, { backgroundColor: sliceColor(s.name, otherColor) }]} />
        <Text variant="caption" numberOfLines={1}>
          {s.name}
        </Text>
        {amounts ? (
          <Text variant="moneySmall" tone="soft">
            {whole(s.amount)}
          </Text>
        ) : null}
      </View>
    ) : (
      <View style={styles.legendRow}>
        <View style={[styles.swatch, { backgroundColor: sliceColor(s.name, otherColor) }]} />
        <Text numberOfLines={1} style={styles.flex}>
          {s.name}
        </Text>
        <Text variant="moneySmall">{whole(s.amount)}</Text>
      </View>
    );
    if (!onPick) return <View key={s.name}>{row}</View>;
    return (
      <Pressable key={s.name} accessibilityRole="button" onPress={() => onPick(s.name)} style={({ pressed }) => pressed && styles.pressed}>
        {row}
      </Pressable>
    );
  });

  if (!legend) return <View style={styles.chartOnly}>{chart}</View>;
  if (below) {
    return (
      <View style={styles.stack}>
        {chart}
        <View style={styles.legendBottom}>{items}</View>
      </View>
    );
  }
  return (
    <View style={styles.row}>
      {chart}
      <View style={styles.legend}>{items}</View>
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    row: { flexDirection: "row", alignItems: "center", gap: space.md },
    chartOnly: { alignItems: "center", justifyContent: "center" },
    stack: { alignItems: "center", gap: space.md },
    legend: { flex: 1, gap: 6, minWidth: 0 },
    legendBottom: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", gap: space.sm },
    legendRow: { flexDirection: "row", alignItems: "center", gap: space.sm },
    tag: { flexDirection: "row", alignItems: "center", gap: 6, maxWidth: 180 },
    swatch: { width: 10, height: 10, borderRadius: 2 },
    flex: { flex: 1, minWidth: 0 },
    pressed: { opacity: 0.6 },
  })
);
