import { useState, type ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useMoney } from "@/features/money/MoneyContext";
import { ApiError, createGoal, createRule, moveBudgetMoney, type ActionProposal, type GoalProposal } from "@/lib/api";
import { formatMoney, SAVE_NAME_SUGGESTIONS, SPEND_CATEGORIES, TRACKING_WINDOWS } from "@/lib/format";
import { useToken } from "@/lib/session";
import { colors, radius, space } from "@/theme/tokens";
import { Button, Text, TextField } from "@/ui";

// Ported from web/src/components/GoalProposalCard.tsx and ActionProposalCard.tsx.
// Nothing is created or changed until the user confirms.

type CardStatus = "pending" | "created" | "dismissed";

const LEGACY_SAVE_NAMES: Record<string, string> = {
  save_amount: "Savings goals",
  pay_off_debt: "Paying off debt",
  build_emergency_fund: "Emergency fund",
};

function defaultSaveName(proposal: GoalProposal): string {
  if (proposal.name?.trim()) return proposal.name.trim();
  return LEGACY_SAVE_NAMES[proposal.type] ?? "";
}

export function GoalProposalCard({ proposal }: { proposal: GoalProposal }) {
  return proposal.type === "track_spending" ? (
    <SpendingTrackerProposalCard proposal={proposal} />
  ) : (
    <SavingsGoalProposalCard proposal={proposal} />
  );
}

function SavingsGoalProposalCard({ proposal }: { proposal: GoalProposal }) {
  const token = useToken();
  const { refresh } = useMoney();
  const [name, setName] = useState(defaultSaveName(proposal));
  const [targetAmount, setTargetAmount] = useState(proposal.target_amount > 0 ? String(proposal.target_amount) : "");
  const [targetDate, setTargetDate] = useState(proposal.target_date ?? "");
  const [status, setStatus] = useState<CardStatus>("pending");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  if (status === "dismissed") return null;
  if (status === "created") return <Done text="Goal set — it's in your money sheet." />;

  async function submit() {
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
    setIsBusy(true);
    try {
      await createGoal(token, { type: "save", name: name.trim() || undefined, target_amount: amount, target_date: targetDate || null });
      setStatus("created");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your goal. Try again.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <ProposalShell
      eyebrow="CREATE THIS GOAL?"
      title="Savings goal"
      detail={
        proposal.at_limit
          ? "You already have 5 goals — finish or drop one before adding another."
          : "Name it and set a target. It'll show up in your money sheet."
      }
    >
      <TextField label="Name" value={name} onChangeText={setName} placeholder="Emergency fund" />
      <Chips options={SAVE_NAME_SUGGESTIONS.map((s) => ({ value: s, label: s }))} value={name} onChange={setName} />
      <TextField label="Target amount ($)" value={targetAmount} onChangeText={setTargetAmount} keyboardType="decimal-pad" />
      <TextField
        label="Target date (optional)"
        value={targetDate}
        onChangeText={setTargetDate}
        placeholder="YYYY-MM-DD"
        keyboardType="numbers-and-punctuation"
      />
      {error && <ErrorText text={error} />}
      <Actions
        confirm="Set goal"
        busy={isBusy}
        disabled={Boolean(proposal.at_limit)}
        onConfirm={submit}
        onDismiss={() => setStatus("dismissed")}
      />
    </ProposalShell>
  );
}

function SpendingTrackerProposalCard({ proposal }: { proposal: GoalProposal }) {
  const token = useToken();
  const { refresh } = useMoney();
  const [category, setCategory] = useState(proposal.category ?? "Dining");
  const [name, setName] = useState(proposal.name?.trim() || proposal.category || "Dining");
  const [windowName, setWindowName] = useState(proposal.window ?? "this_month");
  const [budget, setBudget] = useState(proposal.target_amount > 0 ? String(proposal.target_amount) : "");
  const [status, setStatus] = useState<CardStatus>("pending");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  if (status === "dismissed") return null;
  if (status === "created") return <Done text={`Tracking ${name || category} — it's in your money sheet.`} />;

  async function submit() {
    const amount = budget.trim() === "" ? 0 : Number(budget);
    if (budget.trim() !== "" && (!Number.isFinite(amount) || amount < 0)) {
      setError("Enter a budget of $0 or more, or leave it blank.");
      return;
    }
    setError(null);
    setIsBusy(true);
    try {
      await createGoal(token, {
        type: "track_spending",
        name: name.trim() || undefined,
        target_amount: amount,
        category,
        window: windowName,
      });
      setStatus("created");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save this tracker. Try again.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <ProposalShell
      eyebrow="CREATE THIS GOAL?"
      title="Spending tracker"
      detail={
        proposal.at_limit
          ? "You already have 5 goals — finish or drop one before adding another."
          : "Pick what to watch and over how long."
      }
    >
      <TextField label="Name" value={name} onChangeText={setName} />
      <Text variant="caption" tone="soft">
        What to track
      </Text>
      <Chips
        options={SPEND_CATEGORIES.map((c) => ({ value: c, label: c }))}
        value={category}
        onChange={(next) => {
          // Keep the name in step while it's still the default.
          setName((current) => (!current.trim() || current === category ? next : current));
          setCategory(next);
        }}
      />
      <Text variant="caption" tone="soft">
        Time window
      </Text>
      <Chips options={TRACKING_WINDOWS.map((w) => ({ value: w.id, label: w.label }))} value={windowName} onChange={setWindowName} />
      <TextField
        label="Spending cap ($, optional)"
        value={budget}
        onChangeText={setBudget}
        placeholder="Just track"
        keyboardType="decimal-pad"
      />
      {error && <ErrorText text={error} />}
      <Actions
        confirm="Start tracking"
        busy={isBusy}
        disabled={Boolean(proposal.at_limit)}
        onConfirm={submit}
        onDismiss={() => setStatus("dismissed")}
      />
    </ProposalShell>
  );
}

/** A change the assistant drafted in chat (a rule, a budget move). */
export function ActionProposalCard({ proposal }: { proposal: ActionProposal }) {
  const token = useToken();
  const { refresh } = useMoney();
  const [status, setStatus] = useState<"pending" | "busy" | "done" | "dismissed">("pending");
  const [error, setError] = useState<string | null>(null);
  const { eyebrow, title, detail, confirm, done } = describe(proposal);

  if (status === "dismissed") return null;
  if (status === "done") return <Done text={done} />;

  async function accept() {
    setStatus("busy");
    setError(null);
    try {
      if (proposal.kind === "rule") {
        await createRule(token, {
          merchant_contains: proposal.merchant_contains,
          set_category_id: proposal.category_id,
          set_merchant_name: proposal.set_merchant_name ?? undefined,
          apply_to_existing: true,
        });
      } else {
        await moveBudgetMoney(token, {
          month: proposal.month,
          from_key: proposal.from_key,
          to_key: proposal.to_key,
          amount: proposal.amount,
        });
      }
      setStatus("done");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't do that. Try again.");
      setStatus("pending");
    }
  }

  return (
    <ProposalShell eyebrow={eyebrow} title={title} detail={detail}>
      {error && <ErrorText text={error} />}
      <Actions confirm={confirm} busy={status === "busy"} onConfirm={accept} onDismiss={() => setStatus("dismissed")} />
    </ProposalShell>
  );
}

function describe(p: ActionProposal): { eyebrow: string; title: string; detail: string | null; confirm: string; done: string } {
  switch (p.kind) {
    case "rule":
      return {
        eyebrow: "MAKE THIS A RULE?",
        title: `Always put “${p.merchant_contains}” in ${p.category}`,
        detail:
          [
            p.set_merchant_name ? `Shown as ${p.set_merchant_name}.` : null,
            p.would_change ? `Also updates ${p.would_change} past transaction${p.would_change === 1 ? "" : "s"}.` : null,
          ]
            .filter(Boolean)
            .join(" ") || null,
        confirm: "Make rule",
        done: `Rule saved — “${p.merchant_contains}” now goes to ${p.category}.`,
      };
    case "budget_move":
      return {
        eyebrow: "MOVE BUDGET MONEY?",
        title: `Move ${formatMoney(p.amount)} from ${p.from_name} to ${p.to_name}`,
        detail: `For ${p.month}. ${p.from_name} will have that much less to spend.`,
        confirm: "Move it",
        done: `Moved ${formatMoney(p.amount)} to ${p.to_name}.`,
      };
  }
}

function ProposalShell({
  eyebrow,
  title,
  detail,
  children,
}: {
  eyebrow: string;
  title: string;
  detail: string | null;
  children: ReactNode;
}) {
  return (
    <View style={styles.card}>
      <View style={styles.head}>
        <Text variant="citation" tone="accent">
          {eyebrow}
        </Text>
        <Text variant="heading">{title}</Text>
        {detail ? (
          <Text variant="caption" tone="soft">
            {detail}
          </Text>
        ) : null}
      </View>
      {children}
    </View>
  );
}

function Chips({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
      {options.map((o) => {
        const selected = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            onPress={() => onChange(o.value)}
            style={[styles.chip, selected && styles.chipSelected]}
          >
            <Text variant="caption" tone={selected ? "default" : "soft"}>
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function Actions({
  confirm,
  busy,
  disabled,
  onConfirm,
  onDismiss,
}: {
  confirm: string;
  busy: boolean;
  disabled?: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
}) {
  return (
    <View style={styles.actions}>
      <View style={styles.action}>
        <Button label="Not now" variant="secondary" onPress={onDismiss} />
      </View>
      <View style={styles.action}>
        <Button label={confirm} onPress={onConfirm} loading={busy} disabled={disabled} />
      </View>
    </View>
  );
}

function Done({ text }: { text: string }) {
  return (
    <View style={styles.done}>
      <Text variant="caption" tone="accent">
        ✓ {text}
      </Text>
    </View>
  );
}

function ErrorText({ text }: { text: string }) {
  return (
    <Text variant="caption" tone="negative" accessibilityRole="alert">
      {text}
    </Text>
  );
}

const styles = StyleSheet.create({
  card: {
    alignSelf: "stretch",
    gap: space.md,
    padding: space.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.accentBorder,
    backgroundColor: colors.accentWash,
  },
  head: { gap: space.xs },
  chips: { gap: space.sm },
  chip: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.raised,
  },
  chipSelected: { borderColor: colors.accent },
  actions: { flexDirection: "row", gap: space.sm },
  action: { flex: 1 },
  done: { alignSelf: "stretch", padding: space.lg, borderRadius: radius.lg, backgroundColor: colors.surface },
});
