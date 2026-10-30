import { RefreshControl, ScrollView, StyleSheet } from "react-native";
import { HealthBoard } from "@/features/health/HealthBoard";
import { useMoney } from "@/features/money/MoneyContext";
import { NetWorthCard } from "@/features/money/NetWorthCard";
import { RecapCard } from "@/features/recap/RecapCard";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Screen } from "@/ui";

/**
 * Home: this week's recap, net worth, then health and goals. Chat, transactions
 * and the other boards each have their own tab.
 */
export default function HomeScreen() {
  const styles = useStyles();
  const colors = useColors();
  const { syncFromBank, isSyncing } = useMoney();

  return (
    <Screen padded={false} edges={[]}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isSyncing} onRefresh={syncFromBank} tintColor={colors.accent} />}
      >
        <RecapCard />
        <NetWorthCard />
        <HealthBoard />
      </ScrollView>
    </Screen>
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    content: { padding: space.lg, paddingBottom: space.xxl + space.sm, gap: space.md },
  })
);
