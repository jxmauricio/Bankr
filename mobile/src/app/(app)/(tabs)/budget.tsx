import { router } from "expo-router";
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { BudgetBoard } from "@/features/money/BudgetBoard";
import { useMoney } from "@/features/money/MoneyContext";
import { useFloatingTabInset } from "@/theme/tabBar";
import { space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Icon, Screen } from "@/ui";

/** This month's categories as a budget; add vendors from the corner button. */
export default function BudgetScreen() {
  const styles = useStyles();
  const colors = useColors();
  const tabInset = useFloatingTabInset();
  const { syncFromBank, isSyncing } = useMoney();

  return (
    <Screen padded={false} edges={[]}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: tabInset + 72 }]}
        refreshControl={<RefreshControl refreshing={isSyncing} onRefresh={syncFromBank} tintColor={colors.accent} />}
      >
        <BudgetBoard />
      </ScrollView>
      <View style={[styles.fabWrap, { bottom: tabInset }]} pointerEvents="box-none">
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Add a tracker"
          onPress={() => router.push("/track-new")}
          style={({ pressed }) => [styles.fab, pressed && styles.fabPressed]}
        >
          <Icon name="plus" color={colors.onAccent} size={24} />
        </Pressable>
      </View>
    </Screen>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    content: { paddingBottom: space.xxl },
    fabWrap: { position: "absolute", right: space.lg },
    fab: {
      width: 56,
      height: 56,
      borderRadius: 28,
      backgroundColor: colors.accent,
      alignItems: "center",
      justifyContent: "center",
    },
    fabPressed: { opacity: 0.7 },
  })
);
