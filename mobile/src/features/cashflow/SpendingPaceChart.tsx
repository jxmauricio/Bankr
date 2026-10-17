import { useState } from "react";
import { StyleSheet, View, type GestureResponderEvent } from "react-native";
import Svg, { Circle, Line, Path, Text as SvgText } from "react-native-svg";
import type { SpendingPace } from "@/lib/api";
import { colors, radius, space } from "@/theme/tokens";
import { Card, Text } from "@/ui";
import { whole } from "./flow";

// Ported from web/src/components/SpendingPaceChart.tsx (its compact layout,
// plus touch scrubbing in place of the web's hover tooltip).

/** Rounded-up axis max with a step that gives 4–6 gridlines. */
function niceMax(value: number): { max: number; step: number } {
  const raw = Math.max(value, 100) / 5;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  return { max: Math.ceil(value / step) * step || step, step };
}

/**
 * Where this month ends up if the last week's everyday pace holds. One-off
 * big days (rent, a flight) are left out of the pace, since they won't repeat.
 */
function project(running: number[], daysInMonth: number): number[] {
  const today = running.length;
  const daily = running.map((v, i) => v - (i ? running[i - 1] : 0));
  const positive = daily.filter((d) => d > 0).sort((a, b) => a - b);
  const median = positive.length ? positive[Math.floor(positive.length / 2)] : 0;
  const recent = daily.slice(Math.max(0, today - 7)).filter((d) => d <= median * 3);
  const per = recent.length ? recent.reduce((s, d) => s + Math.max(d, 0), 0) / recent.length : 0;
  const out = [running[today - 1] ?? 0];
  for (let d = today + 1; d <= daysInMonth; d++) out.push(out[out.length - 1] + per);
  return out;
}

const H = 170;
const PAD_B = 16;
const PAD_T = 8;

/**
 * Spending this month vs last month, as running totals by day of month.
 * Drag across the chart to compare the two on any day so far.
 */
export function SpendingPaceChart({ pace }: { pace: SpendingPace }) {
  const [width, setWidth] = useState(0);
  const [scrub, setScrub] = useState<number | null>(null);

  const thisRun = pace.this_month.running;
  const lastRun = pace.last_month.running;
  const today = thisRun.length;
  if (today === 0) return null;

  const days = Math.max(pace.this_month.days_in_month, pace.last_month.days_in_month);
  const proj = project(thisRun, pace.this_month.days_in_month);
  const projEnd = proj[proj.length - 1];
  const lastAt = (d: number) => lastRun[Math.min(d, lastRun.length) - 1] ?? 0;
  const lastTotal = lastRun[lastRun.length - 1] ?? 0;
  const hasLast = lastTotal > 0;
  const { max, step } = niceMax(Math.max(lastTotal, projEnd, thisRun[today - 1]) * 1.05);

  const day = Math.min(scrub ?? today, today);
  const thisV = thisRun[day - 1];
  const lastV = lastAt(day);
  const diff = thisV - lastV;
  const less = diff <= 0;
  const headDiff = thisRun[today - 1] - lastAt(today);
  const headLess = headDiff <= 0;

  const insight = !hasLast
    ? `At this pace you'll finish ${pace.this_month.label} near ${whole(projEnd)}.`
    : headLess
      ? `You've spent ${whole(-headDiff)} less than last month at the same point. At this pace you'll finish near ${whole(projEnd)}${projEnd < lastTotal ? ` — about ${whole(lastTotal - projEnd)} under last month` : ""}.`
      : `You've spent ${whole(headDiff)} more than last month at the same point. At this pace you'll finish near ${whole(projEnd)}.`;

  const x = (d: number) => ((d - 1) / (days - 1)) * width;
  const y = (v: number) => H - PAD_B - (v / max) * (H - PAD_B - PAD_T);
  const path = (vals: number[], from = 1) => vals.map((v, i) => `${i ? "L" : "M"}${x(from + i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const lineThis = path(thisRun);
  const areaThis = `${lineThis} L${x(today).toFixed(1)} ${y(0)} L${x(1)} ${y(0)} Z`;
  const grid = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step).filter((_, i) => i % 2 === 0);

  function pick(e: GestureResponderEvent) {
    if (!width) return;
    const d = Math.round((e.nativeEvent.locationX / width) * (days - 1)) + 1;
    setScrub(Math.max(1, Math.min(today, d)));
  }

  return (
    <Card>
      <Text variant="caption" tone="soft">
        Spending this month · {pace.this_month.label}
      </Text>
      <View style={styles.headline}>
        <Text variant="moneyLarge">{whole(thisRun[today - 1])}</Text>
        {hasLast && (
          <View style={[styles.delta, { backgroundColor: headLess ? colors.positiveWash : colors.negativeWash }]}>
            <Text variant="citation" tone={headLess ? "positive" : "negative"}>
              {headLess ? "▼" : "▲"} {whole(Math.abs(headDiff))} vs last month by day {today}
            </Text>
          </View>
        )}
      </View>
      <Text variant="caption" tone="faint">
        {pace.this_month.days_in_month - today} days left · projected ~{whole(projEnd)}
        {hasLast && ` · last month ended at ${whole(lastTotal)}`}
      </Text>

      {/* The day being compared: today, or wherever a finger is. */}
      <View style={styles.readout}>
        <Text variant="caption" tone="faint">
          {scrub && scrub !== today ? `Day ${day}` : `Today · day ${day}`}
        </Text>
        <Text variant="caption" tone="spend">
          This month {whole(thisV)}
        </Text>
        {hasLast && (
          <Text variant="caption" tone="soft">
            Last {whole(lastV)}{" "}
            <Text variant="caption" tone={less ? "positive" : "negative"}>
              ({less ? "−" : "+"}
              {whole(Math.abs(diff))})
            </Text>
          </Text>
        )}
      </View>

      <View
        style={{ height: H }}
        onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
        onStartShouldSetResponder={() => true}
        onMoveShouldSetResponder={() => true}
        // Keep the gesture while dragging sideways inside the page's scroll view.
        onResponderTerminationRequest={() => false}
        onResponderGrant={pick}
        onResponderMove={pick}
        onResponderRelease={() => setScrub(null)}
        accessible
        accessibilityLabel={`Running spending total. ${pace.this_month.label}: ${whole(thisRun[today - 1])} by day ${today}. ${pace.last_month.label} by day ${today}: ${whole(lastAt(today))}, and ${whole(lastTotal)} in all. Projected: about ${whole(projEnd)}.`}
      >
        {width > 0 && (
          <Svg width={width} height={H}>
            {grid.map((v) => (
              <Line key={v} x1={0} x2={width} y1={y(v)} y2={y(v)} stroke={colors.line} />
            ))}
            <Path d={areaThis} fill={colors.spend} opacity={0.12} />
            {hasLast && <Path d={path(lastRun)} fill="none" stroke={colors.inkSoft} strokeWidth={1.5} strokeDasharray="4 4" />}
            <Path d={path(proj, today)} fill="none" stroke={colors.spend} strokeWidth={2} strokeDasharray="1 4" strokeLinecap="round" />
            <Path d={lineThis} fill="none" stroke={colors.spend} strokeWidth={2.25} strokeLinejoin="round" />
            <Line x1={x(day)} x2={x(day)} y1={0} y2={H - PAD_B} stroke={colors.lineStrong} />
            {hasLast && (
              <>
                <Path d={`M${x(day)} ${y(thisV)} L${x(day)} ${y(lastV)}`} stroke={less ? colors.positive : colors.negative} strokeWidth={2} />
                <Circle cx={x(day)} cy={y(lastV)} r={3.5} fill={colors.surface} stroke={colors.inkSoft} strokeWidth={1.75} />
              </>
            )}
            <Circle cx={x(day)} cy={y(thisV)} r={4.5} fill={colors.spend} stroke={colors.surface} strokeWidth={2} />
            <SvgText x={0} y={H - 2} fontSize={10} fill={colors.inkFaint}>
              1
            </SvgText>
            <SvgText x={width} y={H - 2} textAnchor="end" fontSize={10} fill={colors.inkFaint}>
              {days}
            </SvgText>
          </Svg>
        )}
      </View>

      <View style={styles.legend}>
        <LegendSwatch color={colors.spend} label="This month" />
        {hasLast && <LegendSwatch color={colors.inkSoft} label="Last month" dashed />}
        <LegendSwatch color={colors.spend} label="Projected" dashed />
      </View>
      <View style={styles.insight}>
        <Text variant="caption" tone="soft">
          {insight}
        </Text>
      </View>
    </Card>
  );
}

function LegendSwatch({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <View style={styles.legendItem}>
      <Svg width={18} height={4}>
        <Line x1={0} x2={18} y1={2} y2={2} stroke={color} strokeWidth={dashed ? 2 : 3} strokeDasharray={dashed ? "3 3" : undefined} />
      </Svg>
      <Text variant="caption" tone="soft">
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  headline: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: space.sm },
  delta: { borderRadius: radius.pill, paddingHorizontal: space.sm, paddingVertical: 3 },
  readout: { flexDirection: "row", flexWrap: "wrap", columnGap: space.md, marginTop: space.xs },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: space.md },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  insight: { borderTopColor: colors.line, borderTopWidth: StyleSheet.hairlineWidth, paddingTop: space.sm },
});
