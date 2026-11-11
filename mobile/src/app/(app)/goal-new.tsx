import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { useMoney } from "@/features/money/MoneyContext";
import { ApiError, createGoal } from "@/lib/api";
import { GOAL_KIND_HINTS, GOAL_KIND_LABELS, GOAL_KINDS, SAVE_NAME_SUGGESTIONS, TRACKING_WINDOWS } from "@/lib/format";
import { categoryName, spendCategoryNames, useCategories } from "@/lib/useCategories";
import { useToken } from "@/lib/session";
import { radius, space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Button, Sheet, Text, TextField, ToggleChip } from "@/ui";

type Kind = (typeof GOAL_KINDS)[number];

/** New savings goal or spending tracker. Dedicated sheet — not the accounts page. */
export default function NewGoalSheet() {
  const styles = useStyles();
  const token = useToken();
  const { goals, refresh } = useMoney();
  const categories = useCategories(token);
  const atLimit = goals.active_count >= goals.max_goals;
  const defaultCategory = categoryName(categories, "food_and_dining");

  const [type, setType] = useState<Kind>("save");
  const [name, setName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [category, setCategory] = useState(defaultCategory);
  const [windowName, setWindowName] = useState("this_month");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isTracker = type === "track_spending";

  function pickKind(kind: Kind) {
    setType(kind);
    setError(null);
    setTargetAmount("");
    setName(kind === "track_spending" ? category : "");
  }

  function pickCategory(next: string) {
    setName((current) => (!current.trim() || current === category ? next : current));
    setCategory(next);
  }

  async function submit() {
    if (atLimit) return;
    if (isTracker) {
      const amount = targetAmount.trim() === "" ? 0 : Number(targetAmount);
      if (targetAmount.trim() !== "" && (!Number.isFinite(amount) || amount < 0)) {
        setError("Enter a budget of $0 or more, or leave it blank.");
        return;
      }
      setError(null);
      setBusy(true);
      try {
        await createGoal(token, {
          type: "track_spending",
          name: name.trim() || undefined,
          target_amount: amount,
          category,
          window: windowName,
        });
        await refresh();
        router.back();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Couldn't save this tracker. Try again.");
      } finally {
        setBusy(false);
      }
      return;
    }

    const amount = Number(targetAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Enter a target amount greater than $0.");
      return;
    }
    if (targetDate && !/^\d{4}-\d{2}-\d{2}$/.test(targetDate)) {
      setError("Enter the date as YYYY-MM-DD, or leave it blank.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await createGoal(token, {
        type: "save",
        name: name.trim() || undefined,
        target_amount: amount,
        target_date: targetDate || null,
      });
      await refresh();
      router.back();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your goal. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="New goal"
      footer={
        <Button
          label={busy ? "Saving…" : isTracker ? "Start tracking" : "Set goal"}
          onPress={submit}
          loading={busy}
          disabled={atLimit}
        />
      }
    >
      <Text tone="soft">
        {atLimit
          ? `You already have ${goals.max_goals} goals — delete one before adding another.`
          : "Save toward something, or track spending in a category."}
      </Text>

      <View style={styles.kinds}>
        {GOAL_KINDS.map((kind) => {
          const on = type === kind;
          return (
            <Pressable
              key={kind}
              accessibilityRole="radio"
              accessibilityState={{ selected: on }}
              onPress={() => pickKind(kind)}
              style={[styles.kind, on && styles.kindOn]}
            >
              <Text variant="strong">{GOAL_KIND_LABELS[kind]}</Text>
              <Text variant="caption" tone="soft">
                {GOAL_KIND_HINTS[kind]}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {isTracker ? (
        <>
          <TextField label="Name" value={name} onChangeText={setName} placeholder={category} />
          <Text variant="caption" tone="soft">
            What to track
          </Text>
          <View style={styles.wrap}>
            {spendCategoryNames(categories).map((c) => (
              <ToggleChip key={c} label={c} on={c === category} onToggle={() => pickCategory(c)} />
            ))}
          </View>
          <Text variant="caption" tone="soft">
            Time window
          </Text>
          <View style={styles.wrap}>
            {TRACKING_WINDOWS.map((w) => (
              <ToggleChip key={w.id} label={w.label} on={w.id === windowName} onToggle={() => setWindowName(w.id)} />
            ))}
          </View>
          <TextField
            label="Spending cap (optional)"
            value={targetAmount}
            onChangeText={setTargetAmount}
            placeholder="Just track"
            keyboardType="decimal-pad"
          />
        </>
      ) : (
        <>
          <TextField label="Name" value={name} onChangeText={setName} placeholder="Emergency fund" />
          <View style={styles.wrap}>
            {SAVE_NAME_SUGGESTIONS.map((s) => (
              <ToggleChip key={s} label={s} on={name === s} onToggle={() => setName(s)} />
            ))}
          </View>
          <TextField
            label="Target amount"
            value={targetAmount}
            onChangeText={setTargetAmount}
            placeholder="0"
            keyboardType="decimal-pad"
          />
          <TextField
            label="Target date (optional)"
            value={targetDate}
            onChangeText={setTargetDate}
            placeholder="YYYY-MM-DD"
            keyboardType="numbers-and-punctuation"
          />
        </>
      )}

      {error ? (
        <Text variant="caption" tone="negative" accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
    </Sheet>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    kinds: { gap: space.sm },
    kind: {
      padding: space.md,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.line,
      gap: 4,
      backgroundColor: colors.surface,
    },
    kindOn: { borderColor: colors.accent, backgroundColor: colors.accentWash },
    wrap: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  })
);
