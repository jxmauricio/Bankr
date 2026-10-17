import { router } from "expo-router";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { BankLogo } from "@/features/bank/BankLogos";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import { accountOptions, dateLabel } from "@/features/transactions/filtering";
import { CheckRow, ClearButton } from "@/features/transactions/FilterRows";
import { space } from "@/theme/tokens";
import { Button, Sheet, Text } from "@/ui";

/** Pick any number of accounts, each with its bank's logo and how many transactions it has. */
export default function AccountFilterSheet() {
  const { filters, update, list } = useTransactionFilters();
  const [picked, setPicked] = useState<string[]>(filters.accountIds);
  const options = accountOptions(list.data?.transactions ?? []);
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  return (
    <Sheet
      title="Account"
      trailing={<ClearButton onPress={() => setPicked([])} />}
      footer={
        <Button
          label={picked.length ? `Show ${picked.length} ${picked.length === 1 ? "account" : "accounts"}` : "Show all accounts"}
          onPress={() => {
            update({ accountIds: picked });
            router.back();
          }}
        />
      }
    >
      <Text variant="meta" tone="faint">
        Accounts with transactions · {dateLabel(filters.date)}
      </Text>
      <View accessibilityRole="list">
        {options.map((a) => (
          <CheckRow
            key={a.id}
            checked={picked.includes(a.id)}
            onPress={() => toggle(a.id)}
            leading={<BankLogo name={a.institution} size={28} />}
            label={a.label}
            count={a.count}
          />
        ))}
        {options.length === 0 && (
          <Text tone="soft" align="center" style={styles.empty}>
            No transactions in these dates.
          </Text>
        )}
      </View>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  empty: { padding: space.xl },
});
