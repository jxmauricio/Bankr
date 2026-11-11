import { RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { BankLogo } from "@/features/bank/BankLogos";
import { useLinkBank } from "@/features/bank/useLinkBank";
import { isStale, useMoney } from "@/features/money/MoneyContext";
import { formatMoney, formatRelativeTime } from "@/lib/format";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Button, Card, Text } from "@/ui";

/** The money sheet: net worth and accounts, opened from the net worth card. */
export default function MoneySheet() {
  const styles = useStyles();
  const colors = useColors();
  const { netWorth, syncFromBank, isSyncing, syncError, banksChanged } = useMoney();
  const linking = useLinkBank(banksChanged);
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
            {/* A card balance is normal, not a problem: the minus sign says it's owed, so it stays neutral. Red is for real trouble. */}
            <Text variant="money">
              {formatMoney(account.kind === "liability" ? -account.balance : account.balance)}
            </Text>
          </View>
        ))}
        {linking.error && (
          <Text variant="caption" tone="negative" accessibilityRole="alert">
            {linking.error}
          </Text>
        )}
        <Button label="Link another bank" variant="secondary" onPress={linking.link} loading={linking.busy} />
      </Card>
    </ScrollView>
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    content: {},
    split: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: space.sm },
    flex: { flex: 1 },
  })
);
