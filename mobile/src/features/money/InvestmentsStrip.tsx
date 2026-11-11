import { StyleSheet, View } from "react-native";
import { BankLogo } from "@/features/bank/BankLogos";
import { fetchHoldings, type Holding } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { useResource } from "@/lib/useResource";
import { space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Card, Text } from "@/ui";
import { useMoney } from "./MoneyContext";

/**
 * Brokerage positions with the day's close from the last bank sync. Plaid
 * already sends that price — no separate quote API. Until holdings land
 * (an Item linked before Investments was requested may need a reconnect),
 * fall back to the account totals.
 */
export function InvestmentsStrip() {
  const styles = useStyles();
  const { netWorth, syncVersion } = useMoney();
  const accounts = netWorth.accounts.filter((a) => a.type === "investment");
  const loaded = useResource(fetchHoldings, [syncVersion]);
  if (accounts.length === 0) return null;

  const holdings = loaded.data?.holdings ?? [];
  const accountTotal = accounts.reduce((s, a) => s + a.balance, 0);
  const total = holdings.length > 0 ? holdings.reduce((s, h) => s + h.value, 0) : accountTotal;

  return (
    <Card>
      <Text variant="sectionTitle">Investments</Text>
      <Text variant="moneyLarge">{formatMoney(total)}</Text>
      {holdings.length > 0 ? (
        holdings.map((h, i) => <HoldingRow key={`${h.ticker ?? h.name ?? "pos"}-${i}`} holding={h} />)
      ) : (
        accounts.map((a) => (
          <View key={`${a.institution}-${a.mask}-${a.name}`} style={styles.row}>
            <BankLogo name={a.institution} size={28} />
            <View style={styles.flex}>
              <Text numberOfLines={1}>{a.name ?? a.institution}</Text>
              <Text variant="meta" tone="faint">
                {a.institution}
                {a.mask ? ` •••• ${a.mask}` : ""}
              </Text>
            </View>
            <Text variant="money">{formatMoney(a.balance)}</Text>
          </View>
        ))
      )}
    </Card>
  );
}

function HoldingRow({ holding }: { holding: Holding }) {
  const styles = useStyles();
  const label = holding.ticker ?? holding.name ?? "Position";
  const subtitle = [holding.ticker && holding.name && holding.name !== holding.ticker ? holding.name : null, holding.price != null ? formatMoney(holding.price) : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <View style={styles.row}>
      <View style={styles.ticker}>
        <Text variant="caption" numberOfLines={1}>
          {(holding.ticker ?? "?").slice(0, 5)}
        </Text>
      </View>
      <View style={styles.flex}>
        <Text numberOfLines={1}>{label}</Text>
        {subtitle ? (
          <Text variant="meta" tone="faint" numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      <Text variant="money">{formatMoney(holding.value)}</Text>
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    row: { flexDirection: "row", alignItems: "center", gap: space.sm },
    flex: { flex: 1, minWidth: 0 },
    ticker: {
      width: 44,
      height: 28,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: colors.line,
    },
  })
);
