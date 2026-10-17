import { Pressable, StyleSheet, View } from "react-native";
import { colors, radius, space } from "@/theme/tokens";
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

const styles = StyleSheet.create({
  track: { flexDirection: "row", gap: 2, padding: 3, borderRadius: radius.md, backgroundColor: colors.surface },
  option: {
    flex: 1,
    minHeight: 38,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: space.xs,
    borderRadius: radius.md - 3,
  },
  selected: { backgroundColor: colors.raised },
});
