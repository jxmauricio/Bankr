import { StyleSheet, TextInput, View, type TextInputProps } from "react-native";
import { radius, space, type } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Icon } from "./Icon";

/** A text field with a search glass, for filtering a list in place. */
export function SearchField({ accessibilityLabel, ...rest }: TextInputProps) {
  const styles = useStyles();
  const colors = useColors();
  return (
    <View style={styles.field}>
      <Icon name="search" color={colors.inkFaint} size={18} />
      <TextInput
        placeholderTextColor={colors.inkFaint}
        accessibilityLabel={accessibilityLabel ?? rest.placeholder}
        autoCorrect={false}
        clearButtonMode="while-editing"
        returnKeyType="search"
        style={styles.input}
        {...rest}
      />
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    field: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.sm + 2,
      minHeight: 44,
      paddingHorizontal: space.md + 2,
      borderWidth: 1,
      borderColor: colors.line,
      borderRadius: radius.md,
      backgroundColor: colors.surface,
    },
    input: { ...type.body, flex: 1, color: colors.ink, paddingVertical: space.sm + 2 },
  })
);
