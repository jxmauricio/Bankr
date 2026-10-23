import { StyleSheet, TextInput, View, type TextInputProps } from "react-native";
import { colors, radius, space, type } from "@/theme/tokens";
import { Text } from "./Text";

export function TextField({ label, style, ...rest }: TextInputProps & { label?: string }) {
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

const styles = StyleSheet.create({
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
});
