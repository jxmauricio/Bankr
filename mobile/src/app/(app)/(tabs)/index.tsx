import { RefreshControl, ScrollView, StyleSheet } from "react-native";
import { CreditCardGallery } from "@/features/money/CreditCardGallery";
import { GoalsStrip } from "@/features/money/GoalsStrip";
import { InvestmentsStrip } from "@/features/money/InvestmentsStrip";
import { SpendingStrip } from "@/features/money/SpendingStrip";
import { useMoney } from "@/features/money/MoneyContext";
import { NetWorthCard } from "@/features/money/NetWorthCard";
import { RecapCard } from "@/features/recap/RecapCard";
import { useFloatingTabInset } from "@/theme/tabBar";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Screen } from "@/ui";

/**
 * Home: this week's recap, net worth, spending, accounts, then goals.
 */
export default function HomeScreen() {
  const styles = useStyles();
  const colors = useColors();
  const tabInset = useFloatingTabInset();
  const { syncFromBank, isSyncing } = useMoney();

  return (
    <Screen padded={false} edges={[]}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: tabInset + space.md }]}
        refreshControl={<RefreshControl refreshing={isSyncing} onRefresh={syncFromBank} tintColor={colors.accent} />}
      >
        <RecapCard />
        <NetWorthCard />
        <SpendingStrip />
        <InvestmentsStrip />
        <CreditCardGallery />
        <GoalsStrip />
      </ScrollView>
    </Screen>
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    content: { paddingBottom: space.xxl + space.sm },
  })
);
