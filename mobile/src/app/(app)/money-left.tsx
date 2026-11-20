import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, Pressable, StyleSheet, View } from "react-native";
import { whole } from "@/features/cashflow/flow";
import { bumpMoneyLeft, useBudgetWindow } from "@/features/money/budgetWindow";
import { useMoney } from "@/features/money/MoneyContext";
import {
  ApiError,
  deleteMoneyLeftIncome,
  fetchMoneyLeft,
  upsertMoneyLeftIncome,
  type IncomeCadence,
  type MoneyLeftIncome,
} from "@/lib/api";
import { TRACKING_WINDOWS } from "@/lib/format";
import { useToken } from "@/lib/session";
import { useResource } from "@/lib/useResource";
import { space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Button, Sheet, Text, TextField, ToggleChip } from "@/ui";

const CADENCE_CHIPS: { id: IncomeCadence; label: string }[] = [
  { id: "weekly", label: "Weekly" },
  { id: "biweekly", label: "Every 2 weeks" },
  { id: "monthly", label: "Monthly" },
  { id: "yearly", label: "Yearly" },
];

function paydayLabel(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Expected pay for the window — including paychecks that haven't landed yet. */
export default function MoneyLeftSheet() {
  const styles = useStyles();
  const token = useToken();
  const { syncVersion } = useMoney();
  const [windowName, setWindowName] = useBudgetWindow();
  const plan = useResource((t) => fetchMoneyLeft(t, windowName), [syncVersion, windowName]);
  const data = plan.data;
  const [adding, setAdding] = useState(false);
  const windowLabel = TRACKING_WINDOWS.find((w) => w.id === windowName)?.label ?? "This month";

  async function save(body: Parameters<typeof upsertMoneyLeftIncome>[1]) {
    try {
      await upsertMoneyLeftIncome(token, body, windowName);
      bumpMoneyLeft();
      plan.retry();
      return true;
    } catch (err) {
      Alert.alert("Couldn't save", err instanceof ApiError ? err.message : "Try again in a moment.");
      return false;
    }
  }

  async function remove(id: string) {
    try {
      await deleteMoneyLeftIncome(token, id, windowName);
      bumpMoneyLeft();
      plan.retry();
    } catch (err) {
      Alert.alert("Couldn't delete", err instanceof ApiError ? err.message : "Try again in a moment.");
    }
  }

  return (
    <Sheet title="Coming in" footer={<Button label="Done" onPress={() => router.back()} />}>
      <View style={styles.windows}>
        {TRACKING_WINDOWS.map((w) => (
          <ToggleChip key={w.id} label={w.label} on={w.id === windowName} onToggle={() => setWindowName(w.id)} />
        ))}
      </View>

      {plan.status === "error" && !data ? (
        <Text tone="soft">Couldn't load this.</Text>
      ) : !data ? (
        <Text tone="soft">Adding up expected pay…</Text>
      ) : (
        <>
          <View style={styles.hero}>
            <Text variant="eyebrow" tone="soft" align="center">
              Expected {windowLabel.toLowerCase()}
            </Text>
            <Text variant="moneyLarge" align="center">
              {whole(data.income_total)}
            </Text>
            <Text variant="caption" tone="soft" align="center">
              Pay that should land, including what's still ahead.
            </Text>
          </View>

          {data.incomes.length === 0 ? (
            <Text tone="soft">No paychecks on a schedule yet. Add what you take home.</Text>
          ) : (
            data.incomes.map((row) => (
              <IncomeRow
                key={`${row.origin}-${row.id ?? row.payer ?? row.name}`}
                row={row}
                onSave={save}
                onRemove={row.origin === "custom" && row.id ? () => void remove(row.id!) : undefined}
              />
            ))
          )}
          {adding ? (
            <AddIncome
              onCancel={() => setAdding(false)}
              onSave={async (body) => {
                if (await save(body)) setAdding(false);
              }}
            />
          ) : (
            <Pressable accessibilityRole="button" onPress={() => setAdding(true)} style={({ pressed }) => [styles.add, pressed && styles.pressed]}>
              <Text tone="accent">Add income</Text>
            </Pressable>
          )}
        </>
      )}
    </Sheet>
  );
}

function IncomeRow({
  row,
  onSave,
  onRemove,
}: {
  row: MoneyLeftIncome;
  onSave: (body: Parameters<typeof upsertMoneyLeftIncome>[1]) => Promise<boolean>;
  onRemove?: () => void;
}) {
  const styles = useStyles();
  const [draft, setDraft] = useState(String(row.amount));
  useEffect(() => setDraft(String(row.amount)), [row.amount]);

  function persist(patch: Partial<{ amount: number; cadence: IncomeCadence; included: boolean }>) {
    return onSave({
      id: row.id,
      series_id: row.series_id,
      payer: row.payer,
      name: row.name,
      amount: patch.amount ?? row.amount,
      cadence: patch.cadence ?? row.cadence,
      included: patch.included ?? row.included,
    });
  }

  async function commitAmount() {
    const amount = Number(draft);
    if (!Number.isFinite(amount) || amount < 0 || amount === row.amount) return;
    await persist({ amount });
  }

  const dates = row.dates.map(paydayLabel).join(" · ");

  return (
    <View style={[styles.income, !row.included && styles.skipped]}>
      <View style={styles.incomeHead}>
        <Text variant="strong" style={styles.flex} numberOfLines={1}>
          {row.name}
        </Text>
        <Text variant="money">{row.included ? whole(row.window_amount) : whole(0)}</Text>
      </View>
      <Text variant="caption" tone="faint">
        {dates ? `${dates} · ${whole(row.amount)} each` : row.note}
      </Text>
      <TextField
        label="Each paycheck"
        value={draft}
        onChangeText={setDraft}
        onEndEditing={() => void commitAmount()}
        keyboardType="decimal-pad"
        editable={row.included}
      />
      <View style={styles.windows}>
        {CADENCE_CHIPS.map((c) => (
          <ToggleChip key={c.id} label={c.label} on={c.id === row.cadence} onToggle={() => void persist({ cadence: c.id })} />
        ))}
      </View>
      <View style={styles.incomeHead}>
        {onRemove ? (
          <Pressable accessibilityRole="button" accessibilityLabel={`Remove ${row.name}`} onPress={onRemove} hitSlop={8}>
            <Text variant="caption" tone="negative">
              Delete
            </Text>
          </Pressable>
        ) : (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={row.included ? `Skip ${row.name}` : `Include ${row.name}`}
            onPress={() => void persist({ included: !row.included })}
            hitSlop={8}
          >
            <Text variant="caption" tone="soft">
              {row.included ? "Skip" : "Include"}
            </Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

function AddIncome({
  onCancel,
  onSave,
}: {
  onCancel: () => void;
  onSave: (body: Parameters<typeof upsertMoneyLeftIncome>[1]) => Promise<void>;
}) {
  const styles = useStyles();
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [cadence, setCadence] = useState<IncomeCadence>("monthly");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const n = Number(amount);
    if (!name.trim()) return;
    if (!Number.isFinite(n) || n < 0) return;
    setBusy(true);
    try {
      await onSave({ name: name.trim(), amount: n, cadence, included: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.addForm}>
      <TextField label="Name" value={name} onChangeText={setName} placeholder="Side work, support, a roommate…" />
      <TextField label="Each paycheck" value={amount} onChangeText={setAmount} placeholder="0" keyboardType="decimal-pad" />
      <View style={styles.windows}>
        {CADENCE_CHIPS.map((c) => (
          <ToggleChip key={c.id} label={c.label} on={c.id === cadence} onToggle={() => setCadence(c.id)} />
        ))}
      </View>
      <View style={styles.addActions}>
        <Button label="Cancel" variant="ghost" onPress={onCancel} />
        <Button label={busy ? "Adding…" : "Add"} onPress={() => void submit()} loading={busy} disabled={!name.trim()} />
      </View>
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    windows: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
    flex: { flex: 1, minWidth: 0 },
    hero: { gap: space.xs, paddingVertical: space.sm },
    add: { minHeight: 44, justifyContent: "center" },
    addForm: { gap: space.md, paddingTop: space.sm },
    addActions: { flexDirection: "row", gap: space.sm, justifyContent: "flex-end" },
    income: { gap: space.sm, paddingTop: space.md },
    incomeHead: { flexDirection: "row", alignItems: "baseline", gap: space.sm },
    skipped: { opacity: 0.45 },
    pressed: { opacity: 0.7 },
  })
);
