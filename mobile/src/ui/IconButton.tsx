import { Pressable, StyleSheet } from "react-native";
import { colors, radius } from "@/theme/tokens";
import { Icon, type IconName } from "./Icon";

/** A 44pt square holding one icon: header actions, the composer's send. Always give it a label. */
export function IconButton({
  icon,
  label,
  onPress,
  variant = "secondary",
  disabled = false,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary";
  disabled?: boolean;
}) {
  const primary = variant === "primary";
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      onPress={onPress}
      disabled={disabled}
      hitSlop={4}
      style={({ pressed }) => [styles.base, primary ? styles.primary : styles.secondary, (pressed || disabled) && styles.dimmed]}
    >
      <Icon name={icon} color={primary ? colors.onAccent : colors.inkSoft} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: { width: 44, height: 44, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  primary: { backgroundColor: colors.accent },
  secondary: { backgroundColor: colors.surface },
  dimmed: { opacity: 0.45 },
});
