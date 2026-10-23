import { RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { BankLogo } from "@/features/bank/BankLogos";
import { isStale, useMoney } from "@/features/money/MoneyContext";
import { formatMoney, formatRelativeTime } from "@/lib/format";
import { colors, radius, space } from "@/theme/tokens";
import { Button, Card, Text } from "@/ui";

/** The money sheet: net worth, accounts and goals, opened from the top bar's settings button or the net worth card. */
export default function MoneySheet() {
  const { netWorth, goals, syncFromBank, isSyncing, syncError } = useMoney();
  const stale = isStale(netWorth.as_of) && !isSyncing;

  return (
    <ScrollView
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={isSyncing} onRefresh={syncFromBank} tintColor={colors.accent} />}
    >
      <Card>
        <Text variant="caption" tone="soft">
          Net worth
        </Text>
        <Text variant="moneyLarge">{netWorth.current === null ? "—" : formatMoney(netWorth.current)}</Text>
        <View style={styles.split}>
          <Text variant="caption" tone="soft">
            Assets {formatMoney(netWorth.total_assets ?? 0)}
          </Text>
          <Text variant="caption" tone="soft">
            Debts {formatMoney(netWorth.total_liabilities ?? 0)}
          </Text>
        </View>
        <Text variant="meta" tone={stale ? "warn" : "faint"}>
          {isSyncing
            ? "Refreshing from your bank…"
            : netWorth.as_of
              ? `Synced ${formatRelativeTime(netWorth.as_of)}`
              : "Not synced yet"}
        </Text>
        {syncError && (
          <Text variant="caption" tone="negative" accessibilityRole="alert">
            {syncError}
          </Text>
        )}
        <Button label="Refresh from bank" variant="secondary" onPress={syncFromBank} loading={isSyncing} />
      </Card>

      {goals.goals.length > 0 && (
        <Card>
          <Text variant="heading">Goals</Text>
          {goals.goals.map((goal) => {
            // Same as the web GoalPaceTrack: a tracker with no cap shows what's
            // been spent and its period, with no bar to fill.
            const capped = goal.target_amount > 0;
            const period = goal.type === "track_spending" ? (goal.window_label ?? goal.window ?? "") : "";
            return (
              <View key={goal.id} style={styles.goal}>
                <View style={styles.split}>
                  <Text numberOfLines={1} style={styles.flex}>
                    {goal.name ?? goal.label ?? goal.category ?? "Goal"}
                  </Text>
                  <Text variant="caption" tone="soft">
                    {capped
                      ? `${formatMoney(goal.current_progress_amount)} of ${formatMoney(goal.target_amount)}`
                      : `${formatMoney(goal.current_progress_amount)} spent`}
                    {period ? ` · ${period}` : ""}
                  </Text>
                </View>
                {capped && (
                  <View style={styles.track}>
                    <View
                      style={[
                        styles.fill,
                        {
                          width: `${Math.min(100, Math.max(0, (goal.progress_fraction ?? 0) * 100))}%`,
                          backgroundColor: goal.over_budget ? colors.negative : colors.accent,
                        },
                      ]}
                    />
                  </View>
                )}
              </View>
            );
          })}
        </Card>
      )}

      <Card>
        <Text variant="heading">Accounts</Text>
        {netWorth.accounts.map((account, i) => (
          <View key={`${account.institution}-${account.mask ?? i}`} style={styles.split}>
            <BankLogo name={account.institution} />
            <View style={styles.flex}>
              <Text numberOfLines={1}>{account.name ?? account.institution}</Text>
              <Text variant="meta" tone="faint">
                {account.institution}
                {account.mask ? ` •••• ${account.mask}` : ""}
              </Text>
            </View>
            <Text variant="money" tone={account.kind === "liability" ? "negative" : "default"}>
              {formatMoney(account.kind === "liability" ? -account.balance : account.balance)}
            </Text>
          </View>
        ))}
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, gap: space.md },
  split: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: space.sm },
  flex: { flex: 1 },
  goal: { gap: space.xs },
  track: { height: 6, borderRadius: radius.pill, backgroundColor: colors.line, overflow: "hidden" },
  fill: { height: "100%", borderRadius: radius.pill },
});
