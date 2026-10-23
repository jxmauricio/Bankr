import type { ReactNode } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { openSource } from "@/features/source/openSource";
import type { ChartPoint, ChartSpec } from "@/lib/api";
import { colorForCategory, hasCategoryColor } from "@/lib/chartColors";
import { formatDate, formatMoney } from "@/lib/format";
import { colors, radius, space } from "@/theme/tokens";
import { Text } from "@/ui";
import { openCashFlow } from "./ReplyExtras";

/**
 * The one picture under a chat reply, ported from web/src/components/ChatChart.tsx.
 * The numbers are built server-side from a fresh query, never written by the
 * model. Each kind answers one shape of question: where it went (breakdown),
 * then vs now (compare), how it moved (trend), day by day (daily), one
 * merchant over time (merchant), what's coming up (recurring) and what moved
 * net worth (net_worth).
 *
 * The web lists a tapped bar's rows inline under the chart; on a phone,
 * tapping a bar opens its rows in the transactions sheet instead.
 */
export function ChatChart({ chart }: { chart: ChartSpec }) {
  if (chart.points.length === 0) return null;
  const rowsByPoint = chart.points.some((p) => p.query);

  return (
    <View style={styles.figure} accessible={false}>
      <View style={styles.caption}>
        <Text variant="label" style={styles.flex}>
          {chart.title}
        </Text>
        {chart.period ? (
          <Text variant="citation" tone="faint">
            {chart.period}
          </Text>
        ) : null}
      </View>
      {chart.kind === "breakdown" && <Breakdown chart={chart} />}
      {chart.kind === "compare" && <Compare chart={chart} />}
      {chart.kind === "trend" && <Trend chart={chart} />}
      {chart.kind === "daily" && <Daily chart={chart} />}
      {chart.kind === "merchant" && <Merchant chart={chart} />}
      {chart.kind === "recurring" && <Recurring chart={chart} />}
      {chart.kind === "net_worth" && <NetWorth chart={chart} />}
      {chart.query ? (
        <Pressable onPress={() => openSource(chart.query!, chart.title)} style={styles.footer}>
          <Text variant="caption" tone="accent">
            See every transaction behind this →
          </Text>
        </Pressable>
      ) : rowsByPoint ? (
        <Text variant="caption" tone="faint" style={styles.footer}>
          {chart.kind === "recurring" ? "Tap one to see its past payments." : "Tap an account to see its transactions."}
        </Text>
      ) : (
        <Pressable onPress={openCashFlow} style={styles.footer}>
          <Text variant="caption" tone="accent">
            See the income and spending behind this in Cash flow →
          </Text>
        </Pressable>
      )}
    </View>
  );
}

function barColor(label: string): string {
  if (/^\d+ others$/.test(label)) return colors.inkFaint;
  return hasCategoryColor(label) ? colorForCategory(label) : colors.accent;
}

/** "$71", "$2.1k" -- for labels on narrow bars. */
function shortMoney(value: number): string {
  const abs = Math.abs(value);
  return abs >= 1000 ? `$${(abs / 1000).toFixed(1)}k` : `$${Math.round(abs)}`;
}

function pointSummary(point: ChartPoint): string {
  const share = point.share != null ? `, ${Math.round(point.share * 100)}%` : "";
  return `${point.label}: ${formatMoney(point.value)}${share}${point.partial ? " so far" : ""}`;
}

/** A bar or row that opens its own transactions when it has any. */
function PointButton({
  point,
  summary,
  style,
  children,
}: {
  point: ChartPoint;
  summary?: string;
  style?: object;
  children: ReactNode;
}) {
  const label = summary ?? pointSummary(point);
  if (!point.query) {
    return (
      <View style={style} accessible accessibilityLabel={label}>
        {children}
      </View>
    );
  }
  const query = point.query;
  return (
    <Pressable
      onPress={() => openSource(query, point.label)}
      accessibilityRole="button"
      accessibilityLabel={`${label}. Show these transactions`}
      style={({ pressed }) => [style, pressed && styles.pressed]}
    >
      {children}
    </Pressable>
  );
}

function Bar({ fraction, color }: { fraction: number; color: string }) {
  return (
    <View style={styles.barTrack}>
      <View style={[styles.barFill, { width: `${Math.max(fraction * 100, 2)}%`, backgroundColor: color }]} />
    </View>
  );
}

// --- where it went ------------------------------------------------------------

function Change({ value, previous }: { value: number; previous: number }) {
  const diff = value - previous;
  if (Math.abs(diff) < 0.5)
    return (
      <Text variant="citation" tone="faint">
        same
      </Text>
    );
  // Spending more is the bad direction.
  return (
    <Text variant="citation" tone={diff > 0 ? "negative" : "positive"}>
      {diff > 0 ? "▲" : "▼"} {shortMoney(diff)}
    </Text>
  );
}

function Breakdown({ chart }: { chart: ChartSpec }) {
  const points = chart.points;
  const max = Math.max(...points.map((p) => p.value));
  const hasPrevious = points.some((p) => p.previous != null);
  return (
    <View style={styles.stack}>
      <View style={styles.shareStrip}>
        {points.map((p) => (
          <View key={p.label} style={{ flex: p.share ?? 0, backgroundColor: barColor(p.label) }} />
        ))}
      </View>
      {hasPrevious && (
        <View style={styles.tableHead}>
          <Text variant="citation" tone="faint" style={styles.flex}>
            CATEGORY
          </Text>
          <Text variant="citation" tone="faint">
            {(chart.previous_label ?? "vs before").toUpperCase()}
          </Text>
        </View>
      )}
      {points.map((p, i) => (
        <PointButton
          key={p.label}
          point={p}
          summary={`${pointSummary(p)}${p.previous != null ? `, ${formatMoney(p.previous)} ${chart.previous_label ?? "before"}` : ""}`}
          style={[styles.breakdownRow, i > 0 && styles.rowLine]}
        >
          <View style={styles.rowTop}>
            <View style={[styles.swatch, { backgroundColor: barColor(p.label) }]} />
            <Text variant="caption" tone="soft" numberOfLines={1} style={styles.flex}>
              {p.label}
            </Text>
            {p.previous != null ? (
              <Change value={p.value} previous={p.previous} />
            ) : p.share != null ? (
              <Text variant="citation" tone="faint">
                {Math.round(p.share * 100)}%
              </Text>
            ) : null}
            <Text variant="money" style={styles.amount}>
              {formatMoney(p.value)}
            </Text>
          </View>
          <Bar fraction={max ? p.value / max : 0} color={barColor(p.label)} />
        </PointButton>
      ))}
    </View>
  );
}

// --- then vs now --------------------------------------------------------------

function Compare({ chart }: { chart: ChartSpec }) {
  const [previous, current] = chart.points;
  const max = Math.max(previous.value, current.value);
  const change = chart.change;
  // Spending more is the bad direction, so "up" reads in the negative color.
  const tone = change?.direction === "up" ? "negative" : change?.direction === "down" ? "positive" : "soft";
  const wash =
    change?.direction === "up" ? colors.negativeWash : change?.direction === "down" ? colors.positiveWash : colors.line;
  return (
    <View style={styles.stack}>
      {[
        { point: previous, color: colors.lineStrong },
        { point: current, color: colors.accent },
      ].map(({ point, color }) => (
        <PointButton key={point.label} point={point} style={styles.compareRow}>
          <View style={styles.rowTop}>
            <Text variant="caption" tone="soft" style={styles.flex}>
              {point.label}
            </Text>
            <Text variant="money">{formatMoney(point.value)}</Text>
          </View>
          <Bar fraction={max ? point.value / max : 0} color={color} />
        </PointButton>
      ))}
      {change && (
        <View style={[styles.pill, { backgroundColor: wash }]}>
          <Text variant="citation" tone={tone}>
            {change.direction === "up" ? "▲ +" : change.direction === "down" ? "▼ −" : ""}
            {formatMoney(Math.abs(change.difference))}
            {change.percent_change !== null && ` · ${Math.abs(change.percent_change).toFixed(0)}%`}
          </Text>
        </View>
      )}
    </View>
  );
}

// --- columns: months, days, one merchant -----------------------------------------

/** Vertical bars along a baseline. A bar far above the rest (rent day) is
 * capped and drawn with a break, so the small ones stay readable. */
function Columns({
  chart,
  label,
  valueLabel,
  barColorFor,
  average,
  height = 112,
}: {
  chart: ChartSpec;
  label: (p: ChartPoint) => string;
  valueLabel: (p: ChartPoint, i: number) => string | null;
  barColorFor: (p: ChartPoint, i: number) => string;
  average?: number | null;
  height?: number;
}) {
  const points = chart.points;
  const values = points.map((p) => Math.abs(p.value));
  const sorted = [...values].sort((a, b) => b - a);
  // Cap at 1.25x the second-biggest when the biggest is over 3x it.
  const cap = sorted.length > 2 && sorted[1] > 0 && sorted[0] > sorted[1] * 3 ? sorted[1] * 1.25 : sorted[0] || 1;
  const many = points.length > 14;
  const gap = many ? 2 : 6;
  return (
    <View style={styles.stack}>
      <View style={[styles.columns, { height, gap }]}>
        {average != null && average > 0 && average < cap && (
          <View pointerEvents="none" style={[styles.average, { bottom: `${(average / cap) * 100}%` }]}>
            <Text variant="citation" tone="soft" style={styles.averageLabel}>
              avg {shortMoney(average)}
            </Text>
          </View>
        )}
        {points.map((p, i) => {
          const broken = Math.abs(p.value) > cap;
          const text = valueLabel(p, i);
          const color = barColorFor(p, i);
          return (
            <PointButton key={p.label + i} point={p} style={styles.column}>
              {text && !many ? (
                <Text variant="citation" tone="soft" numberOfLines={1}>
                  {text}
                </Text>
              ) : null}
              <View
                style={[
                  styles.columnBar,
                  {
                    height: `${Math.max((Math.min(Math.abs(p.value), cap) / cap) * 100, p.value ? 4 : 1.5)}%`,
                    // The in-progress period is drawn as an outline.
                    backgroundColor: p.partial ? "transparent" : color,
                    borderColor: p.partial ? colors.spend : color,
                  },
                  p.partial && styles.partial,
                ]}
              >
                {broken && <View style={styles.break} />}
              </View>
            </PointButton>
          );
        })}
      </View>
      <View style={[styles.columnLabels, { gap }]}>
        {points.map((p, i) => (
          <Text key={p.label + i} variant="citation" tone="faint" numberOfLines={1} style={styles.columnLabel}>
            {many && i % 7 !== 0 && i !== points.length - 1 ? "" : label(p)}
            {p.partial && "*"}
          </Text>
        ))}
      </View>
      {points.some((p) => p.partial) && (
        <Text variant="citation" tone="faint">
          * so far
        </Text>
      )}
    </View>
  );
}

function Trend({ chart }: { chart: ChartSpec }) {
  const points = chart.points;
  return (
    <Columns
      chart={chart}
      label={(p) => p.label}
      valueLabel={(p, i) => (i === points.length - 1 ? shortMoney(p.value) : null)}
      barColorFor={(p, i) => (p.value < 0 ? colors.negative : i === points.length - 1 ? colors.accent : colors.lineStrong)}
    />
  );
}

function Daily({ chart }: { chart: ChartSpec }) {
  return (
    <Columns
      chart={chart}
      height={96}
      label={(p) => `${p.weekday ?? ""} ${p.label.split(" ")[1] ?? p.label}`.trim()}
      valueLabel={(p) => (p.value ? shortMoney(p.value) : null)}
      barColorFor={() => colors.spend}
    />
  );
}

function Merchant({ chart }: { chart: ChartSpec }) {
  const peak = Math.max(...chart.points.map((p) => p.value));
  return (
    <View style={styles.stack}>
      <Columns
        chart={chart}
        label={(p) => p.label}
        valueLabel={(p) => (p.value === peak ? shortMoney(p.value) : null)}
        barColorFor={(p) => (p.value === peak ? colors.spend : colors.lineStrong)}
        average={chart.average}
      />
      {chart.stats && chart.stats.length > 0 && (
        <View style={styles.stats}>
          {chart.stats.map((s) => (
            <View key={s.label} style={styles.stat}>
              <Text variant="citation" tone="soft">
                {s.label}
              </Text>
              <Text variant="money">{s.unit === "usd" ? formatMoney(s.value) : s.value}</Text>
              {s.date ? (
                <Text variant="citation" tone="faint">
                  {formatDate(s.date)}
                </Text>
              ) : null}
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

// --- what's coming up ------------------------------------------------------------

function Recurring({ chart }: { chart: ChartSpec }) {
  const today = chart.today ? new Date(`${chart.today}T00:00`) : null;
  const horizon = chart.horizon ? new Date(`${chart.horizon}T00:00`) : null;
  const span = today && horizon ? horizon.getTime() - today.getTime() : 0;
  const upcoming = chart.upcoming ?? [];
  return (
    <View style={styles.stack}>
      {span > 0 && (
        <View
          style={styles.timeline}
          accessible
          accessibilityLabel={`Upcoming charges: ${
            upcoming.map((u) => `${u.label} ${formatDate(u.date)} ${formatMoney(u.value)}`).join(", ") || "none in the next 30 days"
          }`}
        >
          <View style={styles.timelineLine} />
          <Text variant="citation" tone="soft" style={styles.timelineStart}>
            Today
          </Text>
          <Text variant="citation" tone="faint" style={styles.timelineEnd}>
            {formatDate(chart.horizon!)}
          </Text>
          {upcoming.map((u, i) => {
            const at = ((new Date(`${u.date}T00:00`).getTime() - today!.getTime()) / span) * 100;
            return (
              <View key={u.label + u.date} style={[styles.timelineMark, { left: `${Math.min(Math.max(at, 1), 99)}%` }]}>
                <Text variant="citation" tone="soft" style={i % 2 === 0 ? styles.markAbove : styles.markBelow}>
                  {shortMoney(u.value)}
                </Text>
                <View style={styles.dot} />
              </View>
            );
          })}
        </View>
      )}
      <View style={styles.tableHead}>
        <Text variant="citation" tone="faint" style={styles.flex}>
          SERVICE
        </Text>
        <Text variant="citation" tone="faint" style={styles.nextCol}>
          NEXT
        </Text>
        <Text variant="citation" tone="faint" style={styles.amount}>
          MONTHLY
        </Text>
      </View>
      {chart.points.map((p) => (
        <PointButton
          key={p.label}
          point={p}
          summary={`${p.label}: ${formatMoney(p.value)} a month, next ${p.next_date ? formatDate(p.next_date) : "unknown"}${
            p.price_changed ? `, price changed from ${formatMoney(p.typical_amount ?? 0)} to ${formatMoney(p.last_amount ?? 0)}` : ""
          }${p.suggested ? ", not confirmed yet" : ""}`}
          style={[styles.rowTop, styles.recurringRow, styles.rowLine]}
        >
          <View style={[styles.flex, styles.recurringName]}>
            <Text variant="caption" numberOfLines={1}>
              {p.label}
            </Text>
            {p.price_changed && (
              <View style={[styles.pill, { backgroundColor: colors.warnWash }]}>
                <Text variant="citation" tone="warn">
                  Price up
                </Text>
              </View>
            )}
            {p.suggested && (
              <Text variant="citation" tone="faint">
                Suggested
              </Text>
            )}
          </View>
          <Text variant="citation" tone="soft" style={styles.nextCol}>
            {p.next_date ? formatDate(p.next_date) : "—"}
          </Text>
          <Text variant="money" style={styles.amount}>
            {formatMoney(p.value)}
          </Text>
        </PointButton>
      ))}
      <Text variant="caption" tone="faint">
        Next dates are estimated from past charges. Bankr can&apos;t cancel subscriptions — this list is to help you decide.
      </Text>
    </View>
  );
}

// --- what moved net worth ----------------------------------------------------------

function NetWorth({ chart }: { chart: ChartSpec }) {
  const points = chart.points;
  const gains = Math.max(0, ...points.map((p) => p.value));
  const drags = Math.max(0, ...points.map((p) => -p.value));
  const range = gains + drags || 1;
  const zero = (drags / range) * 100;
  const net = points.reduce((sum, p) => sum + p.value, 0);
  return (
    <View style={styles.stack}>
      {points.map((p) => {
        const width = (Math.abs(p.value) / range) * 100;
        const positive = p.value >= 0;
        return (
          <PointButton
            key={p.label}
            point={p}
            summary={`${p.label}: ${positive ? "up" : "down"} ${formatMoney(Math.abs(p.value))}`}
            style={styles.netRow}
          >
            <View style={styles.rowTop}>
              <Text variant="caption" tone={p.note ? "soft" : "default"} numberOfLines={1} style={styles.flex}>
                {p.label}
              </Text>
              <Text variant="citation" tone={positive ? "positive" : "negative"}>
                {positive ? "+" : "−"}
                {formatMoney(Math.abs(p.value))}
              </Text>
            </View>
            <View style={styles.divergeTrack}>
              <View style={[styles.zero, { left: `${zero}%` }]} />
              <View
                style={[
                  styles.diverge,
                  {
                    left: `${positive ? zero : zero - width}%`,
                    width: `${Math.max(width, 1)}%`,
                    backgroundColor: positive ? colors.positive : colors.negative,
                    opacity: p.note ? 0.6 : 1,
                  },
                ]}
              />
            </View>
          </PointButton>
        );
      })}
      <View style={[styles.rowTop, styles.netTotal]}>
        <Text variant="label" style={styles.flex}>
          Net change
        </Text>
        <Text variant="money" tone={net >= 0 ? "positive" : "negative"}>
          {net >= 0 ? "+" : "−"}
          {formatMoney(Math.abs(net))}
        </Text>
      </View>
      <Text variant="caption" tone="faint">
        Each account&apos;s change is the sum of its transactions. Investment growth and interest Bankr can&apos;t see line by
        line show as “Not from transactions”.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  figure: { alignSelf: "stretch", gap: space.md, padding: space.lg, borderRadius: radius.lg, backgroundColor: colors.raised },
  caption: { flexDirection: "row", alignItems: "baseline", gap: space.md },
  flex: { flex: 1 },
  pressed: { opacity: 0.6 },
  stack: { gap: space.sm },
  footer: { borderTopColor: colors.line, borderTopWidth: StyleSheet.hairlineWidth, paddingTop: space.md },
  barTrack: { height: 8, borderRadius: radius.pill, backgroundColor: colors.line, overflow: "hidden" },
  barFill: { height: 8, borderRadius: radius.pill },
  shareStrip: { flexDirection: "row", height: 14, gap: 2, borderRadius: 4, overflow: "hidden" },
  tableHead: { flexDirection: "row", gap: space.md },
  breakdownRow: { gap: 6, paddingVertical: space.sm },
  rowLine: { borderTopColor: colors.line, borderTopWidth: StyleSheet.hairlineWidth },
  rowTop: { flexDirection: "row", alignItems: "center", gap: space.sm },
  swatch: { width: 8, height: 8, borderRadius: 2 },
  amount: { minWidth: 76, textAlign: "right" },
  compareRow: { gap: 4, paddingVertical: 6 },
  pill: { alignSelf: "flex-start", borderRadius: radius.pill, paddingHorizontal: space.sm, paddingVertical: 3 },
  columns: {
    flexDirection: "row",
    alignItems: "flex-end",
    borderBottomColor: colors.lineStrong,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  column: { flex: 1, height: "100%", alignItems: "center", justifyContent: "flex-end", gap: 4, minWidth: 0 },
  columnBar: { width: "100%", maxWidth: 40, borderTopLeftRadius: 6, borderTopRightRadius: 6, overflow: "hidden" },
  partial: { borderWidth: 1, borderBottomWidth: 0, borderStyle: "dashed" },
  break: { position: "absolute", left: 0, right: 0, top: 8, height: 4, backgroundColor: colors.raised, transform: [{ skewY: "-12deg" }] },
  average: {
    position: "absolute",
    left: 0,
    right: 0,
    zIndex: 1,
    borderTopWidth: 1,
    borderStyle: "dashed",
    borderTopColor: colors.inkFaint,
  },
  averageLabel: { position: "absolute", right: 0, top: -16, backgroundColor: colors.raised, paddingHorizontal: 4 },
  columnLabels: { flexDirection: "row" },
  columnLabel: { flex: 1, textAlign: "center" },
  stats: { flexDirection: "row", gap: space.sm },
  stat: { flex: 1, gap: 2, padding: space.sm, borderRadius: radius.md, backgroundColor: colors.surface },
  timeline: { height: 64 },
  timelineLine: { position: "absolute", left: 0, right: 0, top: 32, height: 1, backgroundColor: colors.lineStrong },
  timelineStart: { position: "absolute", left: 0, bottom: 0 },
  timelineEnd: { position: "absolute", right: 0, bottom: 0 },
  timelineMark: { position: "absolute", top: 0, height: 64, width: 0, alignItems: "center" },
  dot: {
    position: "absolute",
    top: 27,
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.accent,
    borderWidth: 2,
    borderColor: colors.raised,
  },
  markAbove: { position: "absolute", top: 8, width: 48, textAlign: "center" },
  markBelow: { position: "absolute", top: 40, width: 48, textAlign: "center" },
  nextCol: { width: 56, textAlign: "right" },
  recurringRow: { minHeight: 44 },
  recurringName: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: space.sm },
  netRow: { gap: 4, paddingVertical: 4 },
  divergeTrack: { height: 16 },
  zero: { position: "absolute", top: 0, bottom: 0, width: 1, backgroundColor: colors.lineStrong },
  diverge: { position: "absolute", top: 2, height: 12, borderRadius: 3 },
  netTotal: { borderTopColor: colors.lineStrong, borderTopWidth: StyleSheet.hairlineWidth, paddingTop: space.sm },
});
