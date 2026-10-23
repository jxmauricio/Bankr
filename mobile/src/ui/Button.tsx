import { ActivityIndicator, Pressable, StyleSheet } from "react-native";
import { radius, space } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Text } from "./Text";

type Variant = "primary" | "secondary" | "ghost";

export function Button({
  label,
  onPress,
  variant = "primary",
  loading = false,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  variant?: Variant;
  loading?: boolean;
  disabled?: boolean;
}) {
  const styles = useStyles();
  const colors = useColors();
  const inactive = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy: loading }}
      onPress={onPress}
      disabled={inactive}
      style={({ pressed }) => [styles.base, styles[variant], (pressed || inactive) && styles.dimmed]}
    >
      {loading ? (
        <ActivityIndicator color={variant === "primary" ? colors.onAccent : colors.ink} />
      ) : (
        <Text variant="label" tone={variant === "primary" ? "onAccent" : "default"}>
          {label}
        </Text>
      )}
    </Pressable>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    base: {
      minHeight: 48,
      borderRadius: radius.md,
      paddingHorizontal: space.lg,
      alignItems: "center",
      justifyContent: "center",
    },
    primary: { backgroundColor: colors.accent },
    secondary: { backgroundColor: colors.raised },
    ghost: { backgroundColor: "transparent" },
    dimmed: { opacity: 0.6 },
  })
);
