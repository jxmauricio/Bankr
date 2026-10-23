import { Pressable, StyleSheet } from "react-native";
import { radius, space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Text } from "./Text";

/** A tappable suggestion or choice: chat starters, clarify answers, retry/edit. */
export function Chip({ label, onPress, disabled = false }: { label: string; onPress: () => void; disabled?: boolean }) {
  const styles = useStyles();
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [styles.chip, (pressed || disabled) && styles.dimmed]}
    >
      <Text variant="label" tone="accent">
        {label}
      </Text>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    chip: {
      minHeight: 40,
      justifyContent: "center",
      paddingHorizontal: space.md + 2,
      borderRadius: radius.md,
      backgroundColor: colors.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: colors.line,
    },
    dimmed: { opacity: 0.5 },
  })
);
