import { router } from "expo-router";
import { useState } from "react";
import { Alert, Pressable, StyleSheet, View } from "react-native";
import { whole } from "@/features/cashflow/flow";
import { ApiError, deleteGoal, type GoalProgress } from "@/lib/api";
import { useToken } from "@/lib/session";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Card, FillBar, Text } from "@/ui";
import { useMoney } from "./MoneyContext";

/** Active goals on Home: add from a dedicated sheet, delete in place. */
export function GoalsStrip() {
  const styles = useStyles();
  const token = useToken();
  const { goals, refresh } = useMoney();
  const list = goals.goals;
  const atLimit = goals.active_count >= goals.max_goals;
  const [removingId, setRemovingId] = useState<string | null>(null);

  function add() {
    router.push("/goal-new");
  }

  function confirmRemove(goal: GoalProgress) {
    const title = goal.name ?? goal.label ?? goal.category ?? "this goal";
    Alert.alert(`Delete ${title}?`, "This stops tracking it. Your transactions stay put.", [
      { text: "Keep", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: () => {
          void remove(goal.id);
        },
      },
    ]);
  }

  async function remove(id: string) {
    setRemovingId(id);
    try {
      await deleteGoal(token, id);
      await refresh();
    } catch (err) {
      Alert.alert("Couldn't delete", err instanceof ApiError ? err.message : "Try again in a moment.");
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <Card>
      <View style={styles.header}>
        <Text variant="sectionTitle">Goals</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: atLimit }}
          onPress={add}
          disabled={atLimit}
        >
          <Text variant="caption" tone={atLimit ? "faint" : "accent"}>
            Add
          </Text>
        </Pressable>
      </View>
      {list.length === 0 ? (
        <Pressable accessibilityRole="button" onPress={add}>
          <Text tone="soft">No goals yet. Add a savings goal or a spending tracker.</Text>
        </Pressable>
      ) : (
        list.map((g) => (
          <GoalRow key={g.id} goal={g} busy={removingId === g.id} onRemove={() => confirmRemove(g)} />
        ))
      )}
      {atLimit && list.length > 0 ? (
        <Text variant="caption" tone="faint">
          {goals.max_goals} is the max — delete one to add another.
        </Text>
      ) : null}
    </Card>
  );
}

function GoalRow({ goal, busy, onRemove }: { goal: GoalProgress; busy: boolean; onRemove: () => void }) {
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
    <View style={[styles.goal, busy && styles.busy]}>
      <View style={styles.top}>
        <Text variant="strong" numberOfLines={1} style={styles.flex}>
          {goal.name ?? goal.label ?? goal.category ?? "Goal"}
        </Text>
        <Text variant="moneySmall" tone="soft">
          {capped ? `${whole(goal.current_progress_amount)} of ${whole(goal.target_amount)}` : `${whole(goal.current_progress_amount)} spent`}
        </Text>
      </View>
      {capped && <FillBar fraction={fraction} color={barColor} />}
      <View style={styles.top}>
        <Text variant="caption" tone="soft" style={styles.flex}>
          {goalNote(goal)}
        </Text>
        <Pressable accessibilityRole="button" accessibilityLabel="Delete goal" onPress={onRemove} hitSlop={8} disabled={busy}>
          <Text variant="caption" tone="negative">
            Delete
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

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

const useStyles = makeStyles(() =>
  StyleSheet.create({
    header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
    flex: { flex: 1, minWidth: 0 },
    goal: { gap: space.sm, paddingTop: space.sm },
    top: { flexDirection: "row", alignItems: "baseline", gap: space.sm },
    busy: { opacity: 0.5 },
  })
);
