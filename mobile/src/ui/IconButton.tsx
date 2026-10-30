import { ActivityIndicator, Pressable, StyleSheet } from "react-native";
import { radius } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Icon, type IconName } from "./Icon";

/** A 44pt square holding one icon: header actions, the composer's send. Always give it a label. */
export function IconButton({
  icon,
  label,
  onPress,
  variant = "secondary",
  disabled = false,
  loading = false,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
  /** "plain" is a bare accent icon, for the top bar. */
  variant?: "primary" | "secondary" | "plain";
  disabled?: boolean;
  loading?: boolean;
}) {
  const styles = useStyles();
  const colors = useColors();
  const primary = variant === "primary";
  const plain = variant === "plain";
  const inactive = disabled || loading;
  const iconColor = primary ? colors.onAccent : plain ? colors.accent : colors.inkSoft;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={loading ? `${label}, in progress` : label}
      accessibilityState={{ disabled: inactive, busy: loading }}
      onPress={onPress}
      disabled={inactive}
      hitSlop={4}
      style={({ pressed }) => [
        styles.base,
        primary ? styles.primary : plain ? null : styles.secondary,
        (pressed || inactive) && styles.dimmed,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={iconColor} />
      ) : (
        <Icon name={icon} color={iconColor} size={plain ? 24 : 20} />
      )}
    </Pressable>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    base: { width: 44, height: 44, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
    primary: { backgroundColor: colors.accent, borderRadius: radius.pill },
    secondary: { backgroundColor: colors.surface },
    dimmed: { opacity: 0.45 },
  })
);
