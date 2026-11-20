import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, Pressable, StyleSheet, View } from "react-native";
import { bumpMoneyLeft } from "@/features/money/budgetWindow";
import { bumpRecurring } from "@/features/transactions/transactionsPage";
import { ApiError, fetchRecurring, updateRecurring, type RecurringKind, type RecurringSeries } from "@/lib/api";
import { useToken } from "@/lib/session";
import { useResource } from "@/lib/useResource";
import { space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Button, SegmentedControl, Sheet, Text, TextField, ToggleChip } from "@/ui";

type OutKind = "subscription" | "bill";

const CADENCE_CHIPS: { id: RecurringSeries["cadence"]; label: string }[] = [
  { id: "weekly", label: "Weekly" },
  { id: "biweekly", label: "Every 2 weeks" },
  { id: "monthly", label: "Monthly" },
  { id: "quarterly", label: "Quarterly" },
  { id: "yearly", label: "Yearly" },
];

/** Fix a detected recurring charge: name, type, cadence, amount, next date. */
export default function RecurringEditSheet() {
  const styles = useStyles();
  const token = useToken();
  const params = useLocalSearchParams<{ id?: string | string[] }>();
  const id = typeof params.id === "string" ? params.id : params.id?.[0];
  const list = useResource(fetchRecurring, [id]);
  const series = list.data?.series.find((s) => s.id === id);

  const [name, setName] = useState("");
  const [kind, setKind] = useState<OutKind>("bill");
  const [cadence, setCadence] = useState<RecurringSeries["cadence"]>("monthly");
  const [amount, setAmount] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [seeded, setSeeded] = useState(false);

  useEffect(() => {
    if (!series || seeded) return;
    setName(series.name);
    setKind(series.kind === "subscription" ? "subscription" : "bill");
    setCadence(series.cadence);
    setAmount(String(series.last_amount));
    setNext(series.next_expected_date);
    setSeeded(true);
  }, [seeded, series]);

  async function save() {
    if (!id) return;
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter an amount greater than $0.");
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(next.trim())) {
      setError("Next charge needs a date like 2026-11-28.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await updateRecurring(token, id, {
        name: name.trim() || series?.name,
        kind: kind as RecurringKind,
        cadence,
        last_amount: value,
        next_expected_date: next.trim(),
        status: series?.status === "suggested" ? "confirmed" : series?.status,
      });
      bumpRecurring();
      bumpMoneyLeft();
      router.back();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save this. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function confirmDismiss() {
    Alert.alert("Not a recurring payment?", "It drops off this list. Transactions stay put.", [
      { text: "Keep", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => void dismiss() },
    ]);
  }

  async function dismiss() {
    if (!id) return;
    setBusy(true);
    try {
      await updateRecurring(token, id, { status: "dismissed" });
      bumpRecurring();
      bumpMoneyLeft();
      router.back();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't remove this. Try again.");
      setBusy(false);
    }
  }

  return (
    <Sheet title={series?.name ?? "Recurring"} footer={<Button label={busy ? "Saving…" : "Save"} onPress={save} loading={busy} />}>
      {list.status === "error" && !series ? (
        <Text tone="soft">Couldn't load this.</Text>
      ) : !list.data ? (
        <Text tone="soft">Loading…</Text>
      ) : !series ? (
        <Text tone="soft">This payment is gone.</Text>
      ) : (
        <>
          <Text tone="soft">Change anything that’s wrong. Save keeps it on Recurring.</Text>
          <TextField label="Name" value={name} onChangeText={setName} />
          <SegmentedControl
            label="Type"
            value={kind}
            onChange={setKind}
            options={[
              { value: "subscription", label: "Subscription" },
              { value: "bill", label: "Bill" },
            ]}
          />
          <Text variant="caption" tone="soft">
            How often
          </Text>
          <View style={styles.wrap}>
            {CADENCE_CHIPS.map((c) => (
              <ToggleChip key={c.id} label={c.label} on={c.id === cadence} onToggle={() => setCadence(c.id)} />
            ))}
          </View>
          <TextField label="Amount" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" />
          <TextField label="Next charge" value={next} onChangeText={setNext} placeholder="YYYY-MM-DD" autoCapitalize="none" />
          {error ? (
            <Text variant="caption" tone="negative" accessibilityRole="alert">
              {error}
            </Text>
          ) : null}
          <Pressable accessibilityRole="button" onPress={confirmDismiss} disabled={busy} style={({ pressed }) => [styles.stop, pressed && styles.pressed]}>
            <Text tone="negative">Not recurring</Text>
          </Pressable>
        </>
      )}
    </Sheet>
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    wrap: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
    stop: { minHeight: 44, justifyContent: "center" },
    pressed: { opacity: 0.6 },
  })
);
