import { router, useLocalSearchParams } from "expo-router";
import { useEffect } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useNotifications } from "@/features/notifications/NotificationsContext";
import { fetchLatestRecap, fetchRecap, type RecapCategory, type RecapGoal, type RecapLine, type WeeklyRecap } from "@/lib/api";
import { colorForCategory } from "@/lib/chartColors";
import { formatMoney } from "@/lib/format";
import { useResource } from "@/lib/useResource";
import { radius, space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Button, Card, ErrorState, groupPosition, Icon, Initial, ListRow, Loading, PageHeader, SectionHeader, Text } from "@/ui";

/**
 * One week's recap: what came in and went out, what it did to each goal,
 * where the money went, and Bankr's take on it. Opening it marks the
 * week's notification read; the arrows page through earlier weeks.
 */
export default function RecapScreen() {
  const styles = useStyles();
  const { week } = useLocalSearchParams<{ week: string }>();
  const { status, data, error, retry, reload, refreshing } = useResource(
    (token) => (week === "latest" ? fetchLatestRecap(token) : fetchRecap(token, week)),
    [week]
  );
  const { markRecapRead } = useNotifications();
  const recap = week === "latest" ? (data?.recap ?? null) : data?.recap?.week_start === week ? data.recap : null;

  useEffect(() => {
    if (week === "latest" && recap?.week_start) router.replace(`/recap/${recap.week_start}`);
  }, [week, recap?.week_start]);

  useEffect(() => {
    if (recap && !recap.read) markRecapRead(recap.week_start);
  }, [recap, markRecapRead]);

  return (
    <SafeAreaView style={styles.root} edges={["top"]}>
      <PageHeader title="Weekly recap" />
      {!recap && status === "error" ? (
        <ErrorState message={error} onRetry={retry} />
      ) : !recap ? (
        <Loading />
      ) : (
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={reload} />}
        >
          <Recap recap={recap} />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function Recap({ recap }: { recap: WeeklyRecap }) {
  const styles = useStyles();
  const colors = useColors();
  const { facts } = recap;
  const goToWeek = (weekStart: string | null) => weekStart && router.setParams({ week: weekStart });

  return (
    <>
      <View style={styles.intro}>
        <View style={styles.weekRow}>
          <WeekArrow direction="previous" onPress={() => goToWeek(recap.previous_week_start)} disabled={!recap.previous_week_start} />
          <Text variant="section" tone="soft">
            {recap.label}
          </Text>
          <WeekArrow direction="next" onPress={() => goToWeek(recap.next_week_start)} disabled={!recap.next_week_start} />
        </View>
        <Text variant="title" align="center">
          {recap.headline}
        </Text>
        <Text variant="meta" tone="faint" align="center">
          {facts.transaction_count === 1 ? "From 1 transaction" : `From ${facts.transaction_count} transactions`}
          {facts.pending_spending > 0 ? ` · ${formatMoney(facts.pending_spending)} still pending` : ""}
        </Text>
      </View>

      {recap.summary ? (
        <Card style={styles.inset}>
          <View style={styles.takeLabel}>
            <Icon name="sparkle" color={colors.accent} size={15} />
            <Text variant="eyebrow" tone="accent">
              Bankr&apos;s take
            </Text>
          </View>
          <Text>{recap.summary}</Text>
        </Card>
      ) : null}

      <Totals recap={recap} />

      {facts.goals.length > 0 && (
        <View>
          <SectionHeader title="Your goals this week" />
          <View style={styles.group}>
            {facts.goals.map((goal, i) => (
              <View key={goal.id} style={i > 0 && styles.divided}>
                {goal.type === "save" ? <SavingsGoal goal={goal} /> : <SpendingGoal goal={goal} />}
              </View>
            ))}
          </View>
        </View>
      )}

      {facts.categories.length > 0 && <WhereItWent categories={facts.categories} />}

      <Lines title="Biggest purchases" lines={facts.biggest_purchases} />
      <Lines title="Money in" lines={facts.money_in_items} credit />

      <View style={styles.actions}>
        <Button
          label="Ask Bankr about this week"
          onPress={() => router.dismissTo({ pathname: "/chat", params: { ask: `How did my week of ${recap.label} go?` } })}
        />
      </View>
    </>
  );
}

function WeekArrow({ direction, onPress, disabled }: { direction: "previous" | "next"; onPress: () => void; disabled: boolean }) {
  const styles = useStyles();
  const colors = useColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={direction === "previous" ? "Previous week" : "Next week"}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      hitSlop={6}
      style={({ pressed }) => [styles.arrow, pressed && styles.pressed]}
    >
      <Icon name={direction === "previous" ? "chevronLeft" : "chevronRight"} color={disabled ? colors.line : colors.accent} size={18} />
    </Pressable>
  );
}

function Totals({ recap }: { recap: WeeklyRecap }) {
  const styles = useStyles();
  const { facts } = recap;
  const typical = facts.typical_week_spending;
  const change = typical ? Math.round(((facts.spending - typical) / typical) * 100) : null;

  return (
    <Card style={styles.inset}>
      <View style={styles.totals}>
        <Total label="Money in" value={facts.money_in > 0 ? `+${formatMoney(facts.money_in)}` : formatMoney(0)} tone={facts.money_in > 0 ? "positive" : "default"} />
        <Total label="Money out" value={formatMoney(facts.money_out)} />
        <Total
          label="Kept"
          value={facts.kept >= 0 ? `+${formatMoney(facts.kept)}` : `−${formatMoney(-facts.kept)}`}
          tone={facts.kept >= 0 ? "positive" : "negative"}
        />
      </View>
      {typical !== null && change !== null && (
        <>
          <View style={styles.hairline} />
          <Text variant="meta" tone="soft">
            {change <= -5 ? (
              <Text variant="meta" tone="positive" style={styles.bold}>
                ↘ {-change}% less{" "}
              </Text>
            ) : change >= 5 ? (
              <Text variant="meta" tone="warn" style={styles.bold}>
                ↗ {change}% more{" "}
              </Text>
            ) : (
              "About the same "
            )}
            spending than your typical week of {formatMoney(typical)}
          </Text>
        </>
      )}
    </Card>
  );
}

function Total({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "positive" | "negative" }) {
  const styles = useStyles();
  return (
    <View style={styles.total}>
      <Text variant="eyebrow" tone="soft">
        {label}
      </Text>
      <Text variant="money" tone={tone} numberOfLines={1} adjustsFontSizeToFit>
        {value}
      </Text>
    </View>
  );
}

function SavingsGoal({ goal }: { goal: Extract<RecapGoal, { type: "save" }> }) {
  const styles = useStyles();
  const colors = useColors();
  const target = goal.target_amount || 1;
  const after = clamp(goal.saved / target);
  const gained = goal.change !== null && goal.change > 0 ? Math.min(goal.change / target, after) : 0;
  const before = after - gained;
  const pct = (fraction: number) => `${Math.round(fraction * 100)}%`;

  return (
    <View style={styles.goal}>
      <GoalTitle
        name={goal.name}
        detail={`${formatMoney(goal.saved)} of ${formatMoney(goal.target_amount)}`}
        status={goal.on_pace === true ? { label: "✓ On track", tone: "positive" } : goal.on_pace === false ? { label: "▼ Behind", tone: "warn" } : null}
      />
      <View style={styles.track}>
        <View style={{ width: `${before * 100}%`, backgroundColor: colors.accent }} />
        {gained > 0 && <View style={[styles.gain, { width: `${gained * 100}%` }]} />}
      </View>
      {goal.change !== null && (
        <Text variant="meta" tone="soft">
          <Text variant="meta" tone={goal.change >= 0 ? "positive" : "negative"} style={styles.bold}>
            {goal.change >= 0 ? `+${formatMoney(goal.change)}` : `−${formatMoney(-goal.change)}`} this week
          </Text>
          {goal.change !== 0 ? ` · ${pct(clamp((goal.saved - goal.change) / target))} → ${pct(after)}` : ""}
        </Text>
      )}
    </View>
  );
}

function SpendingGoal({ goal }: { goal: Extract<RecapGoal, { type: "track_spending" }> }) {
  const styles = useStyles();
  const colors = useColors();
  const limit = goal.target_amount ?? 0;
  const hasLimit = limit > 0;
  const fraction = hasLimit ? clamp(goal.spent / limit) : 0;
  const status = goal.over_budget
    ? ({ label: "▲ Over limit", tone: "negative" } as const)
    : goal.on_pace === false
      ? ({ label: "! Near limit", tone: "warn" } as const)
      : goal.on_pace === true
        ? ({ label: "✓ On track", tone: "positive" } as const)
        : null;
  const fill = goal.over_budget ? colors.negative : goal.on_pace === false ? colors.warn : colors.accent;
  const parts = [
    goal.week_spent !== null ? `${formatMoney(goal.week_spent)} this week` : null,
    goal.remaining !== null && goal.remaining >= 0 ? `${formatMoney(goal.remaining)} left` : null,
  ].filter(Boolean);

  return (
    <View style={styles.goal}>
      <GoalTitle
        name={goal.window_label ? `${goal.name} · ${goal.window_label}` : goal.name}
        detail={hasLimit ? `${formatMoney(goal.spent)} of ${formatMoney(limit)} spent` : `${formatMoney(goal.spent)} spent`}
        status={status}
      />
      {hasLimit && (
        <View style={styles.track}>
          <View style={{ width: `${fraction * 100}%`, backgroundColor: fill }} />
        </View>
      )}
      {parts.length > 0 && (
        <Text variant="meta" tone="soft">
          {parts.join(" · ")}
        </Text>
      )}
    </View>
  );
}

function GoalTitle({
  name,
  detail,
  status,
}: {
  name: string;
  detail: string;
  status: { label: string; tone: "positive" | "warn" | "negative" } | null;
}) {
  const styles = useStyles();
  const colors = useColors();
  const wash = { positive: colors.positiveWash, warn: colors.warnWash, negative: colors.negativeWash };
  return (
    <View style={styles.goalTitle}>
      <View style={styles.flex}>
        <Text variant="label" style={styles.bold}>
          {name}
        </Text>
        <Text variant="meta" tone="soft">
          {detail}
        </Text>
      </View>
      {status && (
        <View style={[styles.status, { backgroundColor: wash[status.tone] }]}>
          <Text variant="eyebrow" tone={status.tone} style={styles.statusText}>
            {status.label}
          </Text>
        </View>
      )}
    </View>
  );
}

function WhereItWent({ categories }: { categories: RecapCategory[] }) {
  const styles = useStyles();
  const total = categories.reduce((sum, c) => sum + c.amount, 0) || 1;
  return (
    <View>
      <SectionHeader title="Where it went" />
      <Card style={styles.inset}>
        <View
          style={styles.stack}
          accessible
          accessibilityRole="image"
          accessibilityLabel={`Spending by category: ${categories.map((c) => `${c.name} ${formatMoney(c.amount)}`).join(", ")}`}
        >
          {categories.map((c) => (
            <View key={c.name} style={{ flex: c.amount / total, backgroundColor: colorForCategory(c.name) }} />
          ))}
        </View>
        {categories.map((c) => (
          <View key={c.name} style={styles.category}>
            <View style={[styles.swatch, { backgroundColor: colorForCategory(c.name) }]} />
            <Text variant="label" style={styles.flex} numberOfLines={1}>
              {c.name}
            </Text>
            <VsUsual category={c} />
            <Text variant="money" style={styles.amount}>
              {formatMoney(c.amount)}
            </Text>
          </View>
        ))}
      </Card>
    </View>
  );
}

function VsUsual({ category }: { category: RecapCategory }) {
  if (category.usual === null) return null;
  const diff = Math.round(category.amount - category.usual);
  if (Math.abs(diff) < 5)
    return (
      <Text variant="meta" tone="faint">
        About usual
      </Text>
    );
  return (
    <Text variant="meta" tone={diff < 0 ? "positive" : "faint"}>
      {diff < 0 ? `−$${-diff}` : `+$${diff}`} vs usual
    </Text>
  );
}

function Lines({ title, lines, credit = false }: { title: string; lines: RecapLine[]; credit?: boolean }) {
  if (lines.length === 0) return null;
  return (
    <View>
      <SectionHeader title={title} />
      {lines.map((line, i) => (
        <ListRow
          key={`${line.merchant}-${line.date}-${i}`}
          title={line.merchant}
          subtitle={[line.category, line.date ? weekdayDate(line.date) : null].filter(Boolean).join(" · ")}
          leading={<Initial name={line.merchant} size={36} />}
          trailing={
            <Text variant="money" tone={credit ? "positive" : "default"}>
              {credit ? `+${formatMoney(line.amount)}` : formatMoney(line.amount)}
            </Text>
          }
          group={groupPosition(i, lines.length)}
        />
      ))}
    </View>
  );
}

function clamp(fraction: number): number {
  return Math.min(1, Math.max(0, fraction));
}

/** "Wed, Oct 15". */
function weekdayDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.bg },
    // Grouped rows and section headers bring their own side margins.
    content: { paddingTop: space.xs, paddingBottom: space.xxl, gap: space.lg },
    intro: { paddingHorizontal: space.lg, gap: 6 },
    weekRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    arrow: { width: 44, height: 32, alignItems: "center", justifyContent: "center" },
    pressed: { opacity: 0.6 },
    takeLabel: { flexDirection: "row", alignItems: "center", gap: 6 },
    totals: { flexDirection: "row", gap: space.sm },
    total: { flex: 1, gap: space.xs },
    hairline: { height: 1, backgroundColor: colors.line, marginVertical: space.xs },
    bold: { fontWeight: "600" },
    group: {
      marginHorizontal: space.lg,
      backgroundColor: colors.surface,
      borderColor: colors.line,
      borderWidth: 1,
      borderRadius: radius.md + 2,
    },
    divided: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.line, marginLeft: space.lg },
    goal: { padding: space.lg, gap: 10 },
    goalTitle: { flexDirection: "row", alignItems: "flex-start", gap: space.md },
    flex: { flex: 1 },
    status: { borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: space.xs },
    statusText: { textTransform: "none", letterSpacing: 0, fontSize: 12 },
    track: { height: 8, borderRadius: radius.pill, backgroundColor: colors.raised, flexDirection: "row", overflow: "hidden" },
    gain: { backgroundColor: colors.positive, borderLeftWidth: 2, borderLeftColor: colors.surface },
    inset: { marginHorizontal: space.lg, gap: space.md },
    stack: { height: 12, borderRadius: radius.pill, flexDirection: "row", gap: 2, overflow: "hidden" },
    category: { flexDirection: "row", alignItems: "center", gap: 10 },
    swatch: { width: 10, height: 10, borderRadius: 5 },
    amount: { minWidth: 80, textAlign: "right" },
    actions: { paddingHorizontal: space.lg, gap: space.xs },
  })
);
