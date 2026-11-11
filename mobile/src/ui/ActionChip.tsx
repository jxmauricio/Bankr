import { Pressable, StyleSheet } from "react-native";
import { radius, space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Text } from "./Text";

type Variant = "accent" | "outline";

/** The chat page's "Open in Cash flow →" control: a pill, not a line of text. */
export function ActionChip({
  label,
  onPress,
  variant = "accent",
}: {
  label: string;
  onPress: () => void;
  variant?: Variant;
}) {
  const styles = useStyles();
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.base, styles[variant], pressed && styles.pressed]}
    >
      <Text variant="label" tone={variant === "accent" ? "accent" : "soft"}>
        {label}
      </Text>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    base: {
      alignSelf: "flex-start",
      paddingHorizontal: space.lg,
      minHeight: 40,
      justifyContent: "center",
      borderRadius: radius.pill,
    },
    accent: { backgroundColor: colors.accentWash },
    outline: { borderWidth: StyleSheet.hairlineWidth, borderColor: colors.lineStrong },
    pressed: { opacity: 0.6 },
  })
);
