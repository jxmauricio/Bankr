import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Pressable, StyleSheet, View } from "react-native";
import { bumpMoneyLeft, useBudgetWindow } from "@/features/money/budgetWindow";
import { useMoney } from "@/features/money/MoneyContext";
import {
  ApiError,
  createGoal,
  deleteGoal,
  fetchMoneyLeft,
  fetchRecurring,
  fetchTransactions,
  updateGoal,
  updateRecurring,
  type RecurringBudgetVendor,
  type RecurringKind,
} from "@/lib/api";
import { TRACKING_WINDOWS, formatMoney } from "@/lib/format";
import { colorForCategory, hasCategoryColor } from "@/lib/chartColors";
import { spendCategoryGroups, useCategories } from "@/lib/useCategories";
import { useToken } from "@/lib/session";
import { useResource } from "@/lib/useResource";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Button, Icon, SearchField, SegmentedControl, Sheet, Text, TextField, ToggleChip } from "@/ui";

type Kind = "category" | "vendor";

type Target = {
  key: string;
  seriesId?: string;
  goalId?: string;
  kind: Kind;
  category: string;
  merchant: string;
};

function targetsFromVendors(vendors: RecurringBudgetVendor[]): Target[] {
  return vendors.map((v) => ({
    key: v.series_id,
    seriesId: v.series_id,
    goalId: v.goal_id ?? undefined,
    kind: "vendor" as const,
    category: "",
    merchant: v.merchant,
  }));
}

function seriesKindForGroup(key: string): RecurringKind {
  return key === "subscriptions" ? "subscription" : "bill";
}

/** New or edited spending tracker. The form is name, window, and limit; a
 * pencil opens the same category/vendor picker as adding one from scratch. */
export default function NewTrackerSheet() {
  const styles = useStyles();
  const colors = useColors();
  const token = useToken();
  const { goals, refresh, syncVersion } = useMoney();
  const categories = useCategories(token);
  const txns = useResource((t) => fetchTransactions(t, "this_month"), [syncVersion]);
  const [budgetWindow] = useBudgetWindow();

  const params = useLocalSearchParams<{
    category?: string | string[];
    merchant?: string | string[];
    goalId?: string | string[];
    group?: string | string[];
  }>();
  const presetCategory = typeof params.category === "string" ? params.category : params.category?.[0];
  const presetMerchant = typeof params.merchant === "string" ? params.merchant : params.merchant?.[0];
  const goalId = typeof params.goalId === "string" ? params.goalId : params.goalId?.[0];
  const groupKey = typeof params.group === "string" ? params.group : params.group?.[0];
  const groupMode = Boolean(groupKey);
  const existing = !groupMode && goalId ? goals.goals.find((g) => g.id === goalId) : undefined;
  const groupGoal = groupMode && goalId ? goals.goals.find((g) => g.id === goalId) : undefined;
  const editing = existing != null;
  const startedWithTarget = Boolean(presetCategory || presetMerchant || goalId || groupKey);

  const [kind, setKind] = useState<Kind>(presetMerchant ? "vendor" : "category");
  const [find, setFind] = useState("");
  const [name, setName] = useState(presetCategory ?? presetMerchant ?? "");
  const [targetAmount, setTargetAmount] = useState("");
  const [category, setCategory] = useState(presetCategory ?? "");
  const [merchant, setMerchant] = useState(presetMerchant ?? "");
  const [windowName, setWindowName] = useState(budgetWindow);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(!startedWithTarget);
  const [targets, setTargets] = useState<Target[]>(() => {
    if (presetMerchant) return [{ key: "preset", kind: "vendor", category: "", merchant: presetMerchant }];
    if (presetCategory) return [{ key: "preset", kind: "category", category: presetCategory, merchant: "" }];
    return [];
  });
  const [slot, setSlot] = useState<number | "new" | null>(null);
  const seeded = useRef(false);

  const plan = useResource((t) => (groupKey ? fetchMoneyLeft(t, windowName) : Promise.resolve(null)), [groupKey, windowName, syncVersion]);
  const group = plan.data?.recurring_groups.find((g) => g.key === groupKey);
  const savableGroup = Boolean(group?.open_as || group?.goal_id || groupGoal);

  const q = find.trim().toLowerCase();
  const groups = spendCategoryGroups(categories);
  const filteredGroups = useMemo(() => {
    return groups
      .map((g) => {
        const kids = g.children.filter((c) => !q || c.toLowerCase().includes(q) || g.name.toLowerCase().includes(q));
        const groupHit = !q || g.name.toLowerCase().includes(q);
        if (!groupHit && kids.length === 0) return null;
        return { name: g.name, options: groupHit ? [g.name, ...g.children] : kids };
      })
      .filter((g): g is { name: string; options: string[] } => g != null);
  }, [groups, q]);

  const vendors = useMemo(() => {
    const map = new Map<string, number>();
    for (const t of txns.data?.transactions ?? []) {
      if (!t.merchant_name || t.amount >= 0) continue;
      map.set(t.merchant_name, (map.get(t.merchant_name) ?? 0) - t.amount);
    }
    return [...map.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([label, amount]) => ({ label, amount }))
      .filter((v) => !q || v.label.toLowerCase().includes(q));
  }, [txns.data, q]);

  useEffect(() => {
    if (groupMode) return;
    if (existing) {
      const vendor = existing.merchant ?? "";
      const cat = existing.category ?? "";
      setKind(vendor ? "vendor" : "category");
      setCategory(cat);
      setMerchant(vendor);
      setFind("");
      setName(existing.name ?? (vendor || cat));
      setWindowName(existing.window ?? "this_month");
      setTargetAmount(existing.target_amount > 0 ? String(existing.target_amount) : "");
      setTargets([{ key: existing.id, goalId: existing.id, kind: vendor ? "vendor" : "category", category: cat, merchant: vendor }]);
      setPicking(false);
      return;
    }
    if (presetCategory) {
      setKind("category");
      setCategory(presetCategory);
      setName((n) => n || presetCategory);
      setPicking(false);
    }
    if (presetMerchant) {
      setKind("vendor");
      setMerchant(presetMerchant);
      setName((n) => n || presetMerchant);
      setPicking(false);
    }
  }, [existing, groupMode, presetCategory, presetMerchant]);

  useEffect(() => {
    if (!group || seeded.current) return;
    seeded.current = true;
    setTargets(targetsFromVendors(group.vendors));
    setName((n) => n || group.name);
    setWindowName(budgetWindow);
    setTargetAmount(group.limit > 0 ? String(Math.round(group.limit)) : "");
    setPicking(false);
  }, [budgetWindow, group]);

  const typedVendor = kind === "vendor" && find.trim().length >= 2 && !vendors.some((v) => v.label.toLowerCase() === q);

  async function reloadGroup() {
    bumpMoneyLeft();
    await refresh();
    if (!groupKey) return;
    const next = await fetchMoneyLeft(token, windowName);
    const g = next.recurring_groups.find((row) => row.key === groupKey);
    setTargets(targetsFromVendors(g?.vendors ?? []));
  }

  async function dropTarget(item: Target) {
    if (item.seriesId) await updateRecurring(token, item.seriesId, { in_budget: false });
    if (item.goalId) await deleteGoal(token, item.goalId);
  }

  async function includeMerchant(label: string) {
    const overview = await fetchRecurring(token);
    const hit = overview.series.find((s) => s.name.toLowerCase() === label.toLowerCase());
    if (hit && groupKey) {
      await updateRecurring(token, hit.id, { status: "confirmed", kind: seriesKindForGroup(groupKey), in_budget: true });
      return;
    }
    await createGoal(token, { type: "track_spending", merchant: label, window: windowName, target_amount: 0 });
  }

  function startEdit(index: number) {
    const item = targets[index];
    setSlot(index);
    setKind(item.kind);
    setFind("");
    setError(null);
    setPicking(true);
  }

  function startAdd() {
    setSlot("new");
    setKind(groupMode ? "vendor" : "category");
    setFind("");
    setError(null);
    setPicking(true);
  }

  function confirmRemove(item: Target) {
    const label = item.merchant || item.category || "this";
    Alert.alert(`Remove ${label} from your budget?`, "Transactions stay put. You can add this back anytime.", [
      { text: "Keep", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => void removeTarget(item) },
    ]);
  }

  async function removeTarget(item: Target) {
    setBusy(true);
    setError(null);
    try {
      if (groupMode) {
        await dropTarget(item);
        await reloadGroup();
      } else if (item.goalId) {
        await deleteGoal(token, item.goalId);
        bumpMoneyLeft();
        await refresh();
        router.back();
        return;
      } else {
        setTargets([]);
        setCategory("");
        setMerchant("");
        setPicking(true);
        setSlot("new");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't remove this. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function pickCategory(next: string) {
    setCategory(next);
    setMerchant("");
    setKind("category");
    setName((current) => (!current.trim() || current === category || current === merchant ? next : current));
    setFind("");
    if (groupMode) {
      await commitGroupPick("category", next, "");
      return;
    }
    setTargets([{ key: "picked", kind: "category", category: next, merchant: "" }]);
    setPicking(false);
    setSlot(null);
  }

  async function pickVendor(next: string) {
    setMerchant(next);
    setCategory("");
    setKind("vendor");
    setName((current) => (!current.trim() || current === category || current === merchant ? next : current));
    setFind("");
    if (groupMode) {
      await commitGroupPick("vendor", "", next);
      return;
    }
    setTargets([{ key: "picked", kind: "vendor", category: "", merchant: next }]);
    setPicking(false);
    setSlot(null);
  }

  async function commitGroupPick(nextKind: Kind, nextCategory: string, nextMerchant: string) {
    const item = typeof slot === "number" ? targets[slot] : null;
    const sameVendor =
      nextKind === "vendor" && item && item.kind === "vendor" && item.merchant.toLowerCase() === nextMerchant.toLowerCase();
    if (sameVendor) {
      setPicking(false);
      setSlot(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (item) await dropTarget(item);
      if (nextKind === "vendor") await includeMerchant(nextMerchant);
      else await createGoal(token, { type: "track_spending", category: nextCategory, window: windowName, target_amount: 0, name: nextCategory });
      await reloadGroup();
      setPicking(false);
      setSlot(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update this tracker. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (groupMode && !savableGroup) {
      router.back();
      return;
    }
    if (!groupMode && kind === "category" && !category) {
      setError("Pick a category.");
      setPicking(true);
      return;
    }
    const vendor = merchant.trim() || (kind === "vendor" ? find.trim() : "");
    if (!groupMode && kind === "vendor" && vendor.length < 2) {
      setError("Pick or type a vendor.");
      setPicking(true);
      return;
    }
    const amount = targetAmount.trim() === "" ? 0 : Number(targetAmount);
    if (targetAmount.trim() !== "" && (!Number.isFinite(amount) || amount < 0)) {
      setError("Enter a limit of $0 or more, or leave it blank.");
      return;
    }
    setError(null);
    setBusy(true);
    const body = {
      name: name.trim() || undefined,
      target_amount: amount,
      category: groupMode ? group?.open_as ?? group?.name : kind === "category" ? category : undefined,
      merchant: groupMode ? undefined : kind === "vendor" ? vendor : undefined,
      window: windowName,
    };
    try {
      const id = groupMode ? group?.goal_id ?? groupGoal?.id : existing?.id;
      if (id) await updateGoal(token, id, body);
      else await createGoal(token, { type: "track_spending", ...body });
      bumpMoneyLeft();
      await refresh();
      router.back();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save this tracker. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function confirmStop() {
    const title = groupMode ? name.trim() || group?.name || "this group" : existing?.name ?? existing?.merchant ?? existing?.category ?? "this tracker";
    Alert.alert(`Remove ${title} from your budget?`, "Transactions stay put. You can add this back anytime.", [
      { text: "Keep", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => void stop() },
    ]);
  }

  async function stop() {
    setBusy(true);
    try {
      if (groupMode) {
        for (const item of targets) await dropTarget(item);
        const groupGoalId = group?.goal_id ?? groupGoal?.id;
        if (groupGoalId) await deleteGoal(token, groupGoalId);
      } else if (existing) {
        await deleteGoal(token, existing.id);
      } else {
        setBusy(false);
        return;
      }
      bumpMoneyLeft();
      await refresh();
      router.back();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't remove this. Try again.");
      setBusy(false);
    }
  }

  const picker = (
    <>
      <SegmentedControl
        label="Track"
        value={kind}
        onChange={(next) => {
          setKind(next);
          setFind("");
          setError(null);
        }}
        options={[
          { value: "category", label: "Category" },
          { value: "vendor", label: "Vendor" },
        ]}
      />
      <SearchField
        value={find}
        onChangeText={setFind}
        placeholder={kind === "category" ? "Find a category" : "Find a vendor"}
      />
      {kind === "category" ? (
        <View>
          {filteredGroups.map((g) => (
            <View key={g.name} style={styles.group}>
              <Text variant="caption" tone="faint">
                {g.name}
              </Text>
              {g.options.map((c) => {
                const on = c === category;
                return (
                  <Pressable
                    key={c}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: on }}
                    onPress={() => void pickCategory(c)}
                    style={({ pressed }) => [styles.option, on && styles.optionOn, pressed && styles.pressed]}
                  >
                    <View
                      style={[styles.swatch, { backgroundColor: hasCategoryColor(c) ? colorForCategory(c) : colors.inkFaint }]}
                    />
                    <Text numberOfLines={1} style={styles.flex}>
                      {c}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          ))}
          {filteredGroups.length === 0 ? (
            <Text tone="soft" align="center">
              No category by that name.
            </Text>
          ) : null}
        </View>
      ) : (
        <View>
          {typedVendor ? (
            <Pressable
              accessibilityRole="button"
              onPress={() => void pickVendor(find.trim())}
              style={({ pressed }) => [styles.option, merchant === find.trim() && styles.optionOn, pressed && styles.pressed]}
            >
              <Text style={styles.flex}>Track “{find.trim()}”</Text>
            </Pressable>
          ) : null}
          {vendors.map((v) => {
            const on = v.label === merchant;
            return (
              <Pressable
                key={v.label}
                accessibilityRole="radio"
                accessibilityState={{ selected: on }}
                onPress={() => void pickVendor(v.label)}
                style={({ pressed }) => [styles.option, on && styles.optionOn, pressed && styles.pressed]}
              >
                <Text numberOfLines={1} style={styles.flex}>
                  {v.label}
                </Text>
                <Text variant="moneySmall" tone="soft">
                  {formatMoney(v.amount)}
                </Text>
              </Pressable>
            );
          })}
          {vendors.length === 0 && !typedVendor ? (
            <Text tone="soft" align="center">
              {q ? "No vendor by that name this month. Type it to track anyway." : "No vendors this month yet."}
            </Text>
          ) : null}
        </View>
      )}
    </>
  );

  const form = (
    <>
      <Text tone="soft">Watch a category or a vendor. A limit is optional.</Text>
      <Text variant="caption" tone="soft">
        Tracking
      </Text>
      {groupMode && plan.status === "error" && targets.length === 0 ? (
        <Text tone="soft">Couldn't load this.</Text>
      ) : groupMode && !plan.data && targets.length === 0 ? (
        <Text tone="soft">Loading…</Text>
      ) : targets.length === 0 ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Choose what to track"
          onPress={startAdd}
          style={({ pressed }) => [styles.tracked, pressed && styles.pressed]}
        >
          <Text variant="strong" numberOfLines={1} style={styles.flex}>
            Choose a category or vendor
          </Text>
          <Icon name="pencil" color={colors.inkFaint} size={18} />
        </Pressable>
      ) : (
        targets.map((item, index) => {
          const label = item.merchant || item.category;
          return (
            <View key={item.key} style={styles.tracked}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Change ${label}`}
                onPress={() => startEdit(index)}
                style={({ pressed }) => [styles.trackedMain, pressed && styles.pressed]}
              >
                {item.kind === "category" && item.category ? (
                  <View
                    style={[styles.swatch, { backgroundColor: hasCategoryColor(item.category) ? colorForCategory(item.category) : colors.inkFaint }]}
                  />
                ) : null}
                <Text variant="strong" numberOfLines={1} style={styles.flex}>
                  {label}
                </Text>
                <Icon name="pencil" color={colors.inkFaint} size={18} />
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Remove ${label}`}
                onPress={() => confirmRemove(item)}
                hitSlop={8}
                style={({ pressed }) => [styles.remove, pressed && styles.pressed]}
              >
                <Icon name="close" color={colors.inkFaint} size={18} />
              </Pressable>
            </View>
          );
        })
      )}
      {groupMode ? (
        <Pressable accessibilityRole="button" onPress={startAdd} style={({ pressed }) => [styles.add, pressed && styles.pressed]}>
          <Icon name="plus" color={colors.accent} size={16} />
          <Text tone="accent">Add</Text>
        </Pressable>
      ) : null}
      <TextField label="Name" value={name} onChangeText={setName} placeholder={group?.name ?? (category || merchant || "Optional")} />
      <Text variant="caption" tone="soft">
        Time window
      </Text>
      <View style={styles.wrap}>
        {TRACKING_WINDOWS.map((w) => (
          <ToggleChip key={w.id} label={w.label} on={w.id === windowName} onToggle={() => setWindowName(w.id)} />
        ))}
      </View>
      <TextField
        label="Limit (optional)"
        value={targetAmount}
        onChangeText={setTargetAmount}
        placeholder="Just track"
        keyboardType="decimal-pad"
      />
      {error ? (
        <Text variant="caption" tone="negative" accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
      {groupMode || editing ? (
        <Pressable accessibilityRole="button" onPress={confirmStop} disabled={busy} style={({ pressed }) => [styles.stop, pressed && styles.pressed]}>
          <Text tone="negative">Remove from budget</Text>
        </Pressable>
      ) : null}
    </>
  );

  return (
    <Sheet
      title={picking ? "What to track" : "Track spending"}
      trailing={
        picking && (targets.length > 0 || slot === "new") ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              setPicking(false);
              setSlot(null);
            }}
            hitSlop={8}
          >
            <Text tone="accent">Done</Text>
          </Pressable>
        ) : undefined
      }
      footer={
        picking ? undefined : (
          <Button
            label={busy ? "Saving…" : groupMode ? (savableGroup ? "Save" : "Done") : editing ? "Save" : "Start tracking"}
            onPress={submit}
            loading={busy}
          />
        )
      }
    >
      {picking ? picker : form}
    </Sheet>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    wrap: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
    group: { paddingTop: space.sm, gap: 2 },
    option: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.sm,
      minHeight: 44,
      paddingVertical: space.xs,
      paddingHorizontal: space.xs,
    },
    optionOn: { backgroundColor: colors.accentWash },
    tracked: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.sm,
      minHeight: 44,
    },
    trackedMain: { flex: 1, minWidth: 0, flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 44 },
    remove: { width: 32, height: 44, alignItems: "center", justifyContent: "center" },
    add: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 44 },
    pressed: { opacity: 0.6 },
    swatch: { width: 8, height: 8, borderRadius: 2 },
    flex: { flex: 1, minWidth: 0 },
    stop: { minHeight: 44, justifyContent: "center" },
  })
);
