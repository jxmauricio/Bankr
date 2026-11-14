import { router } from "expo-router";
import { useState } from "react";
import { Alert, Pressable, StyleSheet, View } from "react-native";
import { whole } from "@/features/cashflow/flow";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import { openActivity } from "@/features/transactions/transactionsPage";
import { counts, DEFAULT_FILTERS, merchantMatches } from "@/features/transactions/filtering";
import { colorForCategory, hasCategoryColor } from "@/lib/chartColors";
import {
  deleteGoal,
  fetchMoneyLeft,
  fetchTransactions,
  updateRecurring,
  type GoalProgress,
  type RecurringBudgetGroup,
  type TransactionRow,
} from "@/lib/api";
import { formatDate, TRACKING_WINDOWS } from "@/lib/format";
import { useToken } from "@/lib/session";
import { merchantOf, signedAmount, topCategories } from "@/lib/transactions";
import { useResource } from "@/lib/useResource";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Card, Icon, Text } from "@/ui";
import { bumpMoneyLeft, useBudgetWindow, useMoneyLeftTick } from "./budgetWindow";
import { useMoney } from "./MoneyContext";
import { TrackingBar } from "./TrackingBar";

/**
 * Leftover money for a chosen window, then envelopes: recurring charges as a
 * jumpstart plus anything you add. Expand a line for recent transactions;
 * the pencil edits it; Remove drops it from Budget. Tap money left to edit pay.
 */
export function BudgetBoard() {
  const styles = useStyles();
  const colors = useColors();
  const token = useToken();
  const { goals, refresh, syncVersion } = useMoney();
  const [windowName] = useBudgetWindow();
  const planTick = useMoneyLeftTick();
  const { update } = useTransactionFilters();
  const plan = useResource((t) => fetchMoneyLeft(t, windowName), [syncVersion, windowName, planTick]);
  const txns = useResource((t) => fetchTransactions(t, windowName), [syncVersion, windowName]);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const trackers = goals.goals.filter((g) => g.type === "track_spending");
  const windowLabel = TRACKING_WINDOWS.find((w) => w.id === windowName)?.label ?? "This month";
  const left = plan.data == null ? null : plan.data.left;
  const comingIn = plan.data == null ? null : plan.data.income_total;
  const recurring = plan.data?.recurring_groups ?? [];
  const budgeted =
    plan.data?.budgeted ??
    trackers.filter((g) => (g.window ?? "this_month") === windowName && g.target_amount > 0).reduce((sum, g) => sum + g.target_amount, 0);
  const saved = comingIn == null ? null : comingIn - budgeted;

  const recurringMerchants = new Set<string>();
  const recurringNames = new Set<string>();
  for (const group of recurring) {
    recurringNames.add(group.name);
    for (const vendor of group.vendors) {
      recurringMerchants.add(vendor.merchant.toLowerCase());
    }
  }

  const rows: BudgetRow[] = [];
  for (const g of trackers) {
    if (g.merchant && recurringMerchants.has(g.merchant.toLowerCase())) continue;
    if (recurringNames.has(g.name ?? "") || recurringNames.has(g.category ?? "")) continue;
    if (recurring.some((group) => group.goal_id === g.id)) continue;
    const vendor = g.merchant ?? "";
    rows.push({
      key: `goal-${g.id}`,
      name: g.name ?? g.merchant ?? g.category ?? "Spending",
      spent: g.current_progress_amount,
      goal: g,
      kind: vendor ? "vendor" : "category",
      vendors: vendor ? [vendor] : [],
      categories: vendor ? [] : [g.category ?? g.name ?? ""].filter(Boolean),
    });
  }

  const allTxns = txns.data?.transactions ?? [];

  function open(row: BudgetRow) {
    const params: Record<string, string> = row.kind === "vendor" ? { merchant: row.name } : { category: row.name };
    if (row.goal) params.goalId = row.goal.id;
    router.push({ pathname: "/track-new", params });
  }

  function openGroup(group: RecurringBudgetGroup) {
    const params: Record<string, string> = { group: group.key };
    if (group.goal_id) params.goalId = group.goal_id;
    router.push({ pathname: "/track-new", params });
  }

  function seeMore(categories: string[], vendors: string[]) {
    update({
      ...DEFAULT_FILTERS,
      date: { kind: "preset", window: windowName },
      categories,
      merchants: vendors,
    });
    openActivity();
    router.navigate("/transactions");
  }

  function confirmRemove(name: string, run: () => Promise<void>) {
    Alert.alert(`Remove ${name} from your budget?`, "Transactions stay put. You can add this back anytime.", [
      { text: "Keep", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => void run() },
    ]);
  }

  async function removeGroup(group: RecurringBudgetGroup) {
    setBusyKey(group.key);
    try {
      for (const vendor of group.vendors) {
        await updateRecurring(token, vendor.series_id, { in_budget: false });
        if (vendor.goal_id) await deleteGoal(token, vendor.goal_id);
      }
      if (group.goal_id) await deleteGoal(token, group.goal_id);
      bumpMoneyLeft();
      await refresh();
    } catch {
      Alert.alert("Couldn't remove this. Try again.");
    } finally {
      setBusyKey(null);
    }
  }

  async function removeRow(row: BudgetRow) {
    setBusyKey(row.key);
    try {
      await deleteGoal(token, row.goal.id);
      bumpMoneyLeft();
      await refresh();
    } catch {
      Alert.alert("Couldn't remove this. Try again.");
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <Card>
      <View style={styles.summary}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Money left, ${left == null ? "loading" : whole(left)}, ${windowLabel}. Edit pay and cash flow.`}
          onPress={() => router.push("/money-left")}
          style={({ pressed }) => [styles.leftHead, pressed && styles.pressed]}
        >
          <Text variant="sectionTitle" style={styles.flex}>
            Money left
          </Text>
          <Text variant="caption" tone="soft">
            {windowLabel}
          </Text>
          <Icon name="chevronRight" color={colors.inkFaint} size={18} />
        </Pressable>
        {left == null && plan.status !== "error" ? (
          <Text variant="moneyLarge" tone="faint" align="center">
            —
          </Text>
        ) : left == null ? (
          <Text tone="soft" align="center">
            Couldn't load money left.
          </Text>
        ) : (
          <Pressable accessibilityRole="button" onPress={() => router.push("/money-left")} style={({ pressed }) => pressed && styles.pressed}>
            <Text variant="moneyLarge" tone={left < 0 ? "negative" : "positive"} align="center">
              {whole(left)}
            </Text>
          </Pressable>
        )}

        <View style={styles.stats}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Coming in, ${comingIn == null ? "loading" : whole(comingIn)}`}
            onPress={() => router.push("/money-left")}
            style={({ pressed }) => [styles.stat, pressed && styles.pressed]}
          >
            <Text variant="eyebrow" tone="soft" align="center">
              Coming in
            </Text>
            <Text variant="money" align="center">
              {comingIn == null ? "—" : whole(comingIn)}
            </Text>
          </Pressable>
          <View style={styles.stat}>
            <Text variant="eyebrow" tone="soft" align="center">
              Budgeted
            </Text>
            <Text variant="money" align="center">
              {whole(budgeted)}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text variant="eyebrow" tone="soft" align="center">
              Saved
            </Text>
            <Text variant="money" tone={saved != null && saved < 0 ? "negative" : "default"} align="center">
              {saved == null ? "—" : whole(saved)}
            </Text>
          </View>
        </View>
      </View>

      {plan.status === "error" && !plan.data && rows.length === 0 ? (
        <Text tone="soft">Couldn't load spending.</Text>
      ) : !plan.data && recurring.length === 0 && rows.length === 0 ? (
        <Text tone="soft">Loading spending…</Text>
      ) : recurring.length === 0 && rows.length === 0 ? (
        <Text tone="soft">Nothing in your budget yet. Recurring charges show up here to start, or tap + to add one.</Text>
      ) : (
        <>
          {recurring.map((group) => {
            const color = hasCategoryColor(group.open_as ?? group.name) ? colorForCategory(group.open_as ?? group.name) : colors.inkFaint;
            const vendors = group.vendors.map((v) => v.merchant);
            return (
              <BudgetLine
                key={group.key}
                name={group.name}
                color={color}
                spent={group.spent}
                limit={group.limit > 0 ? group.limit : null}
                caption={group.vendors.length === 1 ? "1 vendor" : `${group.vendors.length} vendors`}
                open={openKey === group.key}
                onToggle={() => setOpenKey((k) => (k === group.key ? null : group.key))}
                onEdit={() => openGroup(group)}
                editLabel={`Edit ${group.name} tracker`}
                recent={recentFor({ vendors, categories: [] }, allTxns, txns.status)}
                onSeeMore={() => seeMore([], vendors)}
                onRemove={() => confirmRemove(group.name, () => removeGroup(group))}
                removing={busyKey === group.key}
              />
            );
          })}
          {rows.map((row) => {
            const sameWindow = (row.goal.window ?? "this_month") === windowName;
            const limit = sameWindow && row.goal.target_amount > 0 ? row.goal.target_amount : null;
            const spent = sameWindow ? row.goal.current_progress_amount : row.spent;
            const color = hasCategoryColor(row.name) ? colorForCategory(row.name) : colors.inkFaint;
            return (
              <BudgetLine
                key={row.key}
                name={row.name}
                color={color}
                spent={spent}
                limit={limit}
                caption={trackingNote(row.goal, spent, limit)}
                open={openKey === row.key}
                onToggle={() => setOpenKey((k) => (k === row.key ? null : row.key))}
                onEdit={() => open(row)}
                editLabel={`Edit ${row.name} tracker`}
                recent={recentFor({ vendors: row.vendors, categories: row.categories }, allTxns, txns.status)}
                onSeeMore={() => seeMore(row.categories, row.vendors)}
                onRemove={() => confirmRemove(row.name, () => removeRow(row))}
                removing={busyKey === row.key}
              />
            );
          })}
        </>
      )}
    </Card>
  );
}

type BudgetRow = {
  key: string;
  name: string;
  spent: number;
  goal: GoalProgress;
  kind: "category" | "vendor";
  vendors: string[];
  categories: string[];
};

function trackingNote(goal: GoalProgress, spent: number, limit: number | null): string {
  const period = goal.window_label ?? "";
  const watch = goal.category && goal.category !== goal.name && !goal.merchant ? goal.category : "";
  if (limit == null) return [watch, period || "Tracking"].filter(Boolean).join(" · ");
  const remaining = limit - spent;
  const left = remaining < 0 ? `Over by ${whole(-remaining)}` : `${whole(remaining)} left`;
  return [left, watch, period].filter(Boolean).join(" · ");
}

function matchesLine(t: TransactionRow, line: { vendors: string[]; categories: string[] }): boolean {
  if (!counts(t)) return false;
  if (line.vendors.length) return merchantMatches(t, line.vendors);
  return line.categories.some((name) => topCategories(t).includes(name) || t.category === name);
}

function recentFor(
  line: { vendors: string[]; categories: string[] },
  rows: TransactionRow[],
  status: string
): { items: TransactionRow[]; loading: boolean } {
  if (status === "loading" && rows.length === 0) return { items: [], loading: true };
  return {
    items: rows.filter((t) => matchesLine(t, line)).sort((a, b) => b.date.localeCompare(a.date)).slice(0, 5),
    loading: false,
  };
}

function BudgetLine({
  name,
  color,
  spent,
  limit,
  caption,
  open,
  onToggle,
  onEdit,
  editLabel,
  recent,
  onSeeMore,
  onRemove,
  removing,
}: {
  name: string;
  color: string;
  spent: number;
  limit: number | null;
  caption: string | null;
  open: boolean;
  onToggle: () => void;
  onEdit: () => void;
  editLabel: string;
  recent: { items: TransactionRow[]; loading: boolean };
  onSeeMore: () => void;
  onRemove: () => void;
  removing: boolean;
}) {
  const styles = useStyles();
  const colors = useColors();
  return (
    <View style={styles.row}>
      <View style={styles.top}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded: open }}
          accessibilityLabel={`${open ? "Hide" : "Show"} recent transactions for ${name}, ${limit ? `${whole(spent)} of ${whole(limit)}` : `${whole(spent)} spent`}`}
          onPress={onToggle}
          style={({ pressed }) => [styles.toggle, pressed && styles.pressed]}
        >
          <View style={open ? styles.chevronOpen : undefined}>
            <Icon name="chevronDown" color={colors.inkFaint} size={16} />
          </View>
          <View style={[styles.swatch, { backgroundColor: color }]} />
          <Text variant="strong" numberOfLines={1} style={styles.flex}>
            {name}
          </Text>
          <Text variant="moneySmall" tone="soft">
            {limit ? `${whole(spent)} of ${whole(limit)}` : `${whole(spent)} spent`}
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={editLabel}
          onPress={onEdit}
          hitSlop={8}
          style={({ pressed }) => [styles.pencil, pressed && styles.pressed]}
        >
          <Icon name="pencil" color={colors.inkFaint} size={16} />
        </Pressable>
      </View>
      {limit != null ? <TrackingBar spent={spent} limit={limit} /> : null}
      {caption ? (
        <Text variant="caption" tone="soft">
          {caption}
        </Text>
      ) : null}
      {open ? (
        <View style={styles.recent}>
          {recent.loading ? (
            <Text variant="caption" tone="soft">
              Loading…
            </Text>
          ) : recent.items.length === 0 ? (
            <Text variant="caption" tone="soft">
              No transactions in this window.
            </Text>
          ) : (
            recent.items.map((t) => {
              const amount = signedAmount(t.amount);
              return (
                <View key={t.id} style={styles.txn}>
                  <View style={styles.flex}>
                    <Text variant="label" numberOfLines={1}>
                      {merchantOf(t)}
                    </Text>
                    <Text variant="caption" tone="soft">
                      {formatDate(t.date)}
                      {t.is_pending ? " · Pending" : ""}
                    </Text>
                  </View>
                  <Text variant="moneySmall" tone={amount.tone}>
                    {amount.text}
                  </Text>
                </View>
              );
            })
          )}
          <Pressable accessibilityRole="button" onPress={onSeeMore} style={({ pressed }) => [styles.more, pressed && styles.pressed]}>
            <Text tone="accent">See more in Transactions</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Remove ${name} from budget`}
            onPress={onRemove}
            disabled={removing}
            style={({ pressed }) => [styles.more, pressed && styles.pressed]}
          >
            <Text tone="negative">{removing ? "Removing…" : "Remove from budget"}</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    flex: { flex: 1, minWidth: 0 },
    summary: {
      paddingBottom: space.md,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: colors.line,
    },
    leftHead: { flexDirection: "row", alignItems: "center", gap: space.sm },
    row: { gap: space.sm, paddingTop: space.md },
    top: { flexDirection: "row", alignItems: "center", gap: space.xs },
    toggle: { flex: 1, minWidth: 0, flexDirection: "row", alignItems: "center", gap: space.sm },
    chevronOpen: { transform: [{ rotate: "180deg" }] },
    pencil: { width: 32, height: 44, alignItems: "center", justifyContent: "center" },
    swatch: { width: 8, height: 8, borderRadius: 2 },
    stats: { flexDirection: "row", gap: space.md, paddingTop: space.sm },
    stat: { flex: 1, gap: 2, alignItems: "center" },
    recent: { gap: space.sm, paddingTop: space.xs },
    txn: { flexDirection: "row", alignItems: "baseline", gap: space.sm, minHeight: 36 },
    more: { minHeight: 44, justifyContent: "center" },
    pressed: { opacity: 0.7 },
  })
);
