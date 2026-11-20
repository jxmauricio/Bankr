import { router } from "expo-router";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { useMoney } from "@/features/money/MoneyContext";
import { ApiError, createGoal } from "@/lib/api";
import { SAVE_NAME_SUGGESTIONS } from "@/lib/format";
import { useToken } from "@/lib/session";
import { space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Button, Sheet, Text, TextField, ToggleChip } from "@/ui";

/** New savings goal. Tracking has its own sheet. */
export default function NewGoalSheet() {
  const styles = useStyles();
  const token = useToken();
  const { goals, refresh } = useMoney();
  const atLimit = goals.active_count >= goals.max_goals;

  const [name, setName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (atLimit) return;
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
      footer={<Button label={busy ? "Saving…" : "Set goal"} onPress={submit} loading={busy} disabled={atLimit} />}
    >
      <Text tone="soft">
        {atLimit
          ? `You already have ${goals.max_goals} goals — delete one before adding another.`
          : "Put money toward something — a trip, a cushion, paying off debt."}
      </Text>

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

      {error ? (
        <Text variant="caption" tone="negative" accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
    </Sheet>
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    wrap: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  })
);
