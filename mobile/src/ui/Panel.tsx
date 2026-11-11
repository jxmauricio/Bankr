import type { ReactNode } from "react";
import { StyleSheet, View, type ViewStyle } from "react-native";
import { radius, space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";

/** A raised, rounded block like a chat chart: sits on the flat page so it reads as a thing. */
export function Panel({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  const styles = useStyles();
  return <View style={[styles.panel, style]}>{children}</View>;
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    panel: {
      marginHorizontal: space.lg,
      marginTop: space.md,
      padding: space.lg,
      borderRadius: radius.lg,
      backgroundColor: colors.raised,
      gap: space.sm,
    },
  })
);
