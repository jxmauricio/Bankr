import { router } from "expo-router";
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import Svg, { Circle } from "react-native-svg";
import { whole } from "@/features/cashflow/flow";
import { useMoney } from "@/features/money/MoneyContext";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import { DEFAULT_FILTERS } from "@/features/transactions/filtering";
import { fetchHealth, type GoalProgress, type HealthMetric, type HealthTone, type SpendingHealth } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { radius, space, type Tone } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Card, ErrorState, Loading, Screen, Text } from "@/ui";

/**
 * A score out of 100, the four metrics behind it, then goal progress: the
 * Health board of the Bankr iOS Redesign canvas. The score and metrics come
 * from /dashboard/health; goals are the ones the shell already loaded.
 */
export default function HealthScreen() {
  const styles = useStyles();
  const colors = useColors();
  const { goals, syncFromBank, isSyncing, syncVersion } = useMoney();
  const health = useResource(fetchHealth, [syncVersion]);
  const { update } = useTransactionFilters();
  const h = health.data;

  function openMetric(m: HealthMetric) {
    if (m.id === "saved") return router.navigate("/cash-flow");
    if (m.id === "emergency_fund") return router.push("/money");
    // The rest are categories, by key; show their transactions over the same
    // months. Rows are filtered by category name.
    const name = h?.categories.find((c) => c.id === m.id)?.name ?? m.name;
    update({ ...DEFAULT_FILTERS, date: h ? { kind: "custom", start: h.start, end: h.end } : DEFAULT_FILTERS.date, categories: [name] });
    router.navigate("/transactions");
  }

  return (
    // The tab bar above owns the top inset.
    <Screen padded={false} edges={[]}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isSyncing} onRefresh={syncFromBank} tintColor={colors.accent} />}
      >
        {health.status === "error" && !h ? (
          <Card>
            <ErrorState message="Couldn't load your financial health." onRetry={health.retry} />
          </Card>
        ) : !h ? (
          <Card style={styles.placeholder}>
            <Loading />
          </Card>
        ) : h.income <= 0 || h.score === null ? (
          <Card>
            <Text tone="soft" align="center">
              No income in linked accounts for {h.label}, so there’s nothing to score against.
            </Text>
          </Card>
        ) : (
          <>
            <ScoreCard health={h} />
            <View style={styles.grid}>
              {h.metrics.map((m) => (
                <Pressable
                  key={m.id}
                  accessibilityRole="button"
                  onPress={() => openMetric(m)}
                  style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
                >
                  <Text variant="eyebrow" tone="soft">
                    {m.name}
                  </Text>
                  <Text variant="figure">{formatMetric(m)}</Text>
                  <Text variant="label" tone={TONE[m.tone]} style={styles.status}>
                    {statusLabel(m)}
                  </Text>
                </Pressable>
              ))}
            </View>
          </>
        )}

        <GoalsCard goals={goals.goals} />

        {h && h.score !== null && (
          <Text variant="caption" tone="faint" style={styles.note}>
            {h.partial ? `This month so far · ${h.label}, scaled to a full month.` : `Average of ${h.label}.`} {h.note}
          </Text>
        )}
      </ScrollView>
    </Screen>
  );
}

const TONE: Record<HealthTone, Tone> = { good: "positive", ok: "warn", high: "negative", neutral: "soft" };

function formatMetric(m: HealthMetric): string {
  if (m.value === null) return "—";
  if (m.unit === "months") return `${m.value.toFixed(1)} mo`;
  return `${Math.round(m.value)}%`;
}

function statusLabel(m: HealthMetric): string {
  if (m.tone === "good") return "Healthy";
  if (m.tone === "ok") return "Watch";
  if (m.tone === "high") return m.higher_is_better ? "Low" : "High";
  return m.id === "emergency_fund" ? "No balances yet" : "—";
}

function scoreWords(h: SpendingHealth): { headline: string; detail: string } {
  const score = h.score ?? 0;
  const scored = h.metrics.filter((m) => m.points !== null);
  const best = scored.reduce((a, b) => ((b.points ?? 0) > (a.points ?? 0) ? b : a));
  const worst = scored.reduce((a, b) => ((b.points ?? 0) < (a.points ?? 0) ? b : a));
  const name = (m: HealthMetric) => m.name.toLowerCase();
  if (score >= 80) {
    return {
      headline: "Looking good",
      detail: (worst.points ?? 100) < 70 ? `Keep an eye on ${name(worst)}.` : `Your ${name(best)} is doing the heavy lifting.`,
    };
  }
  if (score >= 60) return { headline: "Getting there", detail: `${worst.name} is holding the score back.` };
  return { headline: "Needs attention", detail: `Start with ${name(worst)}: it's furthest from its guideline.` };
}

const RING = { size: 116, stroke: 12, r: 50 };

function ScoreCard({ health }: { health: SpendingHealth }) {
  const styles = useStyles();
  const colors = useColors();
  const score = health.score ?? 0;
  const { headline, detail } = scoreWords(health);
  const ringColor = score >= 80 ? colors.positive : score >= 60 ? colors.warn : colors.negative;
  const circumference = 2 * Math.PI * RING.r;

  return (
    <Card style={styles.score}>
      <View style={styles.ring}>
        <Svg width={RING.size} height={RING.size} viewBox="0 0 120 120" accessibilityLabel={`Financial health score ${score} out of 100`}>
          <Circle cx={60} cy={60} r={RING.r} fill="none" stroke={colors.line} strokeWidth={RING.stroke} />
          <Circle
            cx={60}
            cy={60}
            r={RING.r}
            fill="none"
            stroke={ringColor}
            strokeWidth={RING.stroke}
            strokeLinecap="round"
            strokeDasharray={`${(score / 100) * circumference} ${circumference}`}
            transform="rotate(-90 60 60)"
          />
        </Svg>
        <View style={styles.ringLabel} pointerEvents="none">
          <Text variant="display">{score}</Text>
          <Text variant="eyebrow" tone="soft">
            Score
          </Text>
        </View>
      </View>
      <View style={styles.scoreText}>
        <Text variant="caption" tone="soft">
          {health.label}
        </Text>
        <Text variant="title">{headline}</Text>
        <Text tone="soft">{detail}</Text>
      </View>
    </Card>
  );
}

function GoalsCard({ goals }: { goals: GoalProgress[] }) {
  const styles = useStyles();
  return (
    <Card style={styles.goals}>
      <View style={styles.goalsHeader}>
        <Text variant="section" tone="soft">
          Goals
        </Text>
        <Text variant="section" tone="soft">
          Progress
        </Text>
      </View>
      {goals.length === 0 ? (
        <Text tone="soft" style={styles.goal}>
          No goals yet. Ask Bankr to set one up.
        </Text>
      ) : (
        goals.map((g) => <GoalRow key={g.id} goal={g} />)
      )}
      <View style={styles.goalActions}>
        <Pressable
          accessibilityRole="button"
          onPress={() => router.navigate({ pathname: "/", params: { ask: "Help me set up a new goal." } })}
          style={({ pressed }) => [styles.goalAction, pressed && styles.pressed]}
        >
          <Text variant="section" tone="accent">
            Add a goal
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push("/money")}
          style={({ pressed }) => [styles.goalAction, styles.goalActionLine, pressed && styles.pressed]}
        >
          <Text variant="section" tone="accent">
            Edit goals
          </Text>
        </Pressable>
      </View>
    </Card>
  );
}

function GoalRow({ goal }: { goal: GoalProgress }) {
  const styles = useStyles();
  const colors = useColors();
  const capped = goal.target_amount > 0;
  const fraction = Math.min(1, Math.max(0, goal.progress_fraction ?? 0));
  const tracking = goal.type === "track_spending";
  const barColor = tracking
    ? goal.over_budget
      ? colors.negative
      : colors.accent
    : goal.on_pace === false
      ? colors.warn
      : colors.positive;

  return (
    <View style={styles.goal}>
      <View style={styles.goalTop}>
        <Text variant="strong" numberOfLines={1} style={styles.flex}>
          {goal.name ?? goal.label ?? goal.category ?? "Goal"}
        </Text>
        <Text variant="moneySmall" tone="soft">
          {capped ? `${whole(goal.current_progress_amount)} of ${whole(goal.target_amount)}` : `${whole(goal.current_progress_amount)} spent`}
        </Text>
      </View>
      {capped && (
        <View style={styles.track}>
          <View style={[styles.fill, { width: `${fraction * 100}%`, backgroundColor: barColor }]} />
        </View>
      )}
      <Text variant="caption" tone="soft">
        {goalNote(goal)}
      </Text>
    </View>
  );
}

/** "Mar 2027" from "2027-03-15". */
function monthYear(iso: string): string {
  const [year, month] = iso.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

function goalNote(goal: GoalProgress): string {
  const period = goal.window_label ?? "";
  if (goal.type === "track_spending") {
    if (goal.target_amount <= 0) return period;
    const remaining = goal.remaining_amount ?? goal.target_amount - goal.current_progress_amount;
    const left = remaining < 0 ? `Over by ${whole(-remaining)}` : `${whole(remaining)} left`;
    return period ? `${left} · ${period}` : left;
  }
  const remaining = goal.target_amount - goal.current_progress_amount;
  if (remaining <= 0) return "Reached";
  if (!goal.target_date) return `${Math.round((goal.progress_fraction ?? 0) * 100)}% of the way`;
  if (goal.on_pace) return `On pace for ${monthYear(goal.target_date)}`;
  const [year, month] = goal.target_date.split("-").map(Number);
  const now = new Date();
  const monthsLeft = Math.max(1, (year - now.getFullYear()) * 12 + (month - 1 - now.getMonth()));
  return `${whole(remaining / monthsLeft)} a month to make it by ${monthYear(goal.target_date)}`;
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    content: { padding: space.lg, paddingBottom: space.xxl + space.sm, gap: space.md },
    placeholder: { height: 160 },
    pressed: { opacity: 0.6 },
    flex: { flex: 1 },
    score: { flexDirection: "row", alignItems: "center", gap: space.lg + 2 },
    ring: { width: RING.size, height: RING.size },
    ringLabel: { position: "absolute", top: 0, right: 0, bottom: 0, left: 0, alignItems: "center", justifyContent: "center" },
    scoreText: { flex: 1, gap: space.xs + 2 },
    grid: { flexDirection: "row", flexWrap: "wrap", gap: space.sm + 2 },
    tile: {
      // Two to a row, less half the gap between them.
      flexBasis: "47%",
      flexGrow: 1,
      backgroundColor: colors.surface,
      borderColor: colors.line,
      borderWidth: 1,
      borderRadius: radius.md + 2,
      padding: space.md + 2,
      gap: space.xs + 2,
    },
    status: { fontSize: 13, fontWeight: "600" },
    goals: { padding: 0, gap: 0, overflow: "hidden" },
    goalsHeader: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: space.lg, paddingTop: space.md + 2, paddingBottom: space.xs },
    goal: { paddingHorizontal: space.lg, paddingTop: space.sm + 2, paddingBottom: space.md + 2, gap: space.sm },
    goalTop: { flexDirection: "row", alignItems: "baseline", gap: space.sm },
    track: { height: 8, borderRadius: radius.pill, backgroundColor: colors.line, overflow: "hidden" },
    fill: { height: 8, borderRadius: radius.pill },
    goalActions: { flexDirection: "row", borderTopColor: colors.line, borderTopWidth: 1 },
    goalAction: { flex: 1, height: 46, alignItems: "center", justifyContent: "center" },
    goalActionLine: { borderLeftColor: colors.line, borderLeftWidth: 1 },
    note: { paddingHorizontal: space.xs },
  })
);
