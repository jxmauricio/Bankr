import type { ReactNode } from "react";
import { StyleSheet, View, type ViewStyle } from "react-native";
import { space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  const styles = useStyles();
  return <View style={[styles.card, style]}>{children}</View>;
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    card: {
      backgroundColor: colors.bg,
      borderColor: colors.lineStrong,
      borderBottomWidth: 1,
      borderRadius: 0,
      paddingHorizontal: space.lg,
      paddingTop: space.xl,
      paddingBottom: space.xl,
      gap: space.md,
    },
  })
);
