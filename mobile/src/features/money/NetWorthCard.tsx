import { router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import Animated, { Easing, useAnimatedProps, useSharedValue, withTiming } from "react-native-reanimated";
import Svg, { Circle, Path } from "react-native-svg";
import { formatMoney } from "@/lib/format";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Card, RegisterAmount, Text } from "@/ui";
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
const AnimatedPath = Animated.createAnimatedComponent(Path);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

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
    <Card>
      <Text variant="sectionTitle">Net worth</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Your money, ${netWorth.current === null ? "unknown" : formatMoney(netWorth.current)}`}
        onPress={() => router.push("/money")}
        style={({ pressed }) => [styles.figure, pressed && styles.pressed]}
      >
        {change !== null && (
          <Text variant="label" tone={up ? "positive" : "negative"}>
            {up ? "↗" : "↘"} {pct !== null ? `${Math.abs(pct).toFixed(1)}%` : formatMoney(Math.abs(change))}
          </Text>
        )}
        {netWorth.current === null ? (
          <Text variant="moneyLarge" style={styles.amount}>
            —
          </Text>
        ) : (
          <View style={styles.ticker}>
            <RegisterAmount value={netWorth.current} />
          </View>
        )}
      </Pressable>

      <View style={styles.chart} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
        {width > 0 && points.length > 1 && <Line key={range} points={points} width={width} color={up ? colors.positive : colors.negative} />}
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
    </Card>
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
  const length = Math.max(
    1,
    xy.reduce((n, p, i) => (i === 0 ? 0 : n + Math.hypot(p[0] - xy[i - 1][0], p[1] - xy[i - 1][1])), 0)
  );

  const drawn = useSharedValue(0);
  useEffect(() => {
    drawn.set(0);
    drawn.set(withTiming(1, { duration: 1100, easing: Easing.out(Easing.cubic) }));
  }, [drawn]);

  const lineProps = useAnimatedProps(() => ({
    strokeDashoffset: length * (1 - drawn.get()),
  }));
  const fillProps = useAnimatedProps(() => ({
    opacity: 0.1 * drawn.get(),
  }));
  const dotProps = useAnimatedProps(() => ({
    opacity: drawn.get() > 0.88 ? (drawn.get() - 0.88) / 0.12 : 0,
  }));

  return (
    <Svg width={width} height={CHART_HEIGHT} accessibilityElementsHidden>
      <AnimatedPath d={`${line} L${lastX} ${CHART_HEIGHT} L${pad} ${CHART_HEIGHT} Z`} fill={color} fillOpacity={0} animatedProps={fillProps} />
      <AnimatedPath
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={`${length} ${length}`}
        animatedProps={lineProps}
      />
      <AnimatedCircle cx={lastX} cy={lastY} r={4.5} fill={colors.raised} stroke={color} strokeWidth={2.5} opacity={0} animatedProps={dotProps} />
    </Svg>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    figure: { alignItems: "center", gap: 2 },
    pressed: { opacity: 0.6 },
    amount: { fontSize: 36 },
    ticker: { height: 40, overflow: "hidden", borderRadius: 1 },
    chart: { height: CHART_HEIGHT },
    ranges: { flexDirection: "row", justifyContent: "center", gap: 6 },
    range: {
      minWidth: 44,
      height: 30,
      paddingHorizontal: space.md,
      alignItems: "center",
      justifyContent: "center",
      borderBottomWidth: 2,
      borderBottomColor: "transparent",
    },
    rangeOn: { borderBottomColor: colors.ink },
  })
);
