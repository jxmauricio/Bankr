import { router } from "expo-router";
import { useMemo, useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import Svg, { Circle, Path } from "react-native-svg";
import { formatMoney } from "@/lib/format";
import { radius, space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Text } from "@/ui";
import { useMoney } from "./MoneyContext";

const RANGES = [
  { id: "1W", days: 7 },
  { id: "1M", days: 30 },
  { id: "3M", days: 91 },
  { id: "YTD", days: null },
  { id: "1Y", days: 365 },
] as const;

type RangeId = (typeof RANGES)[number]["id"];

const CHART_HEIGHT = 84;

/**
 * Net worth, its change over the chosen range, and a line of the history.
 * Tapping the figure opens the money sheet (accounts and goals).
 */
export function NetWorthCard() {
  const styles = useStyles();
  const colors = useColors();
  const { netWorth } = useMoney();
  const [range, setRange] = useState<RangeId>("1M");
  const [width, setWidth] = useState(0);

  const points = useMemo(() => {
    const spec = RANGES.find((r) => r.id === range)!;
    const start = new Date();
    if (spec.days === null) start.setMonth(0, 1);
    else start.setDate(start.getDate() - spec.days);
    const from = start.toISOString().slice(0, 10);
    return netWorth.history.filter((p) => p.date >= from).map((p) => p.net_worth);
  }, [netWorth.history, range]);

  const change = points.length > 1 ? points[points.length - 1] - points[0] : null;
  const pct = change !== null && points[0] !== 0 ? (change / Math.abs(points[0])) * 100 : null;
  const up = (change ?? 0) >= 0;

  return (
    <View style={styles.card}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Your money"
        onPress={() => router.push("/money")}
        style={({ pressed }) => [styles.figure, pressed && styles.pressed]}
      >
        {change !== null && (
          <Text variant="label" tone={up ? "positive" : "negative"}>
            {up ? "↗" : "↘"} {pct !== null ? `${Math.abs(pct).toFixed(1)}%` : formatMoney(Math.abs(change))}
          </Text>
        )}
        <Text variant="moneyLarge" style={styles.amount}>
          {netWorth.current === null ? "—" : formatMoney(netWorth.current)}
        </Text>
        <Text variant="caption" tone="soft">
          net worth
        </Text>
      </Pressable>

      <View style={styles.chart} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
        {width > 0 && points.length > 1 && <Line points={points} width={width} color={up ? colors.positive : colors.negative} />}
      </View>

      <View accessibilityRole="radiogroup" accessibilityLabel="Range" style={styles.ranges}>
        {RANGES.map((r) => {
          const on = r.id === range;
          return (
            <Pressable
              key={r.id}
              accessibilityRole="radio"
              accessibilityState={{ checked: on }}
              onPress={() => setRange(r.id)}
              style={[styles.range, on && styles.rangeOn]}
            >
              <Text variant="caption" tone={on ? "default" : "faint"}>
                {r.id}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function Line({ points, width, color }: { points: number[]; width: number; color: string }) {
  const colors = useColors();
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const pad = 6;
  const xy = points.map((v, i) => [
    pad + (i / (points.length - 1)) * (width - pad * 2),
    pad + (1 - (v - min) / span) * (CHART_HEIGHT - pad * 2),
  ]);
  const line = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const [lastX, lastY] = xy[xy.length - 1];
  return (
    <Svg width={width} height={CHART_HEIGHT} accessibilityElementsHidden>
      <Path d={`${line} L${lastX} ${CHART_HEIGHT} L${pad} ${CHART_HEIGHT} Z`} fill={color} fillOpacity={0.08} />
      <Path d={line} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
      <Circle cx={lastX} cy={lastY} r={4.5} fill={colors.surface} stroke={color} strokeWidth={2.5} />
    </Svg>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    card: {
      backgroundColor: colors.surface,
      borderColor: colors.line,
      borderWidth: 1,
      borderRadius: radius.md + 2,
      paddingTop: space.lg + 2,
      paddingBottom: space.md + 2,
      paddingHorizontal: space.lg,
      gap: space.md,
    },
    figure: { alignItems: "center", gap: 2 },
    pressed: { opacity: 0.6 },
    amount: { fontSize: 36 },
    chart: { height: CHART_HEIGHT },
    ranges: { flexDirection: "row", justifyContent: "center", gap: 6 },
    range: { minWidth: 44, height: 30, paddingHorizontal: space.md, borderRadius: 15, alignItems: "center", justifyContent: "center" },
    rangeOn: { backgroundColor: colors.raised },
  })
);
