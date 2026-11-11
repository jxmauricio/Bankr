import { Pressable, StyleSheet, View } from "react-native";
import { space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { Text } from "./Text";

/** Equal-width, mutually exclusive options in one track. Keep labels short (the design uses "3 months", "Year"). */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  const styles = useStyles();
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={label} style={styles.track}>
      {options.map((o) => {
        const selected = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            onPress={() => onChange(o.value)}
            style={[styles.option, selected && styles.selected]}
          >
            <Text variant="caption" tone={selected ? "default" : "soft"} numberOfLines={1}>
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    track: {
      flexDirection: "row",
      borderBottomColor: colors.line,
      borderBottomWidth: StyleSheet.hairlineWidth,
      backgroundColor: colors.bg,
    },
    option: {
      flex: 1,
      minHeight: 40,
      alignItems: "center",
      justifyContent: "center",
      paddingHorizontal: space.xs,
      borderBottomWidth: 2,
      borderBottomColor: "transparent",
    },
    selected: { borderBottomColor: colors.ink },
  })
);
