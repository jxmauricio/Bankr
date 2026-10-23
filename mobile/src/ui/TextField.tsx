import { StyleSheet, TextInput, View, type TextInputProps } from "react-native";
import { radius, space, type } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Text } from "./Text";

export function TextField({ label, style, ...rest }: TextInputProps & { label?: string }) {
  const styles = useStyles();
  const colors = useColors();
  return (
    <View style={styles.wrap}>
      {label && (
        <Text variant="caption" tone="soft">
          {label}
        </Text>
      )}
      <TextInput placeholderTextColor={colors.inkFaint} style={[styles.input, style]} {...rest} />
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    wrap: { gap: space.xs },
    input: {
      ...type.body,
      color: colors.ink,
      backgroundColor: colors.surface,
      borderColor: colors.line,
      borderWidth: 1,
      borderRadius: radius.md,
      minHeight: 44,
      paddingHorizontal: space.md + 2,
      paddingVertical: space.sm + 2,
    },
  })
);
