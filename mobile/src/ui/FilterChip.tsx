import { Pressable, StyleSheet, View } from "react-native";
import { colors, radius, space } from "@/theme/tokens";
import { Icon, type IconName } from "./Icon";
import { Text } from "./Text";

/**
 * One filter in a chip row. Inactive: an outline with "Label ▾". Active: filled
 * with its value, and an × that clears it when `onClear` is given. Tapping the
 * chip itself opens that filter's sheet.
 */
export function FilterChip({
  label,
  active,
  icon,
  onPress,
  onClear,
}: {
  label: string;
  active: boolean;
  icon?: IconName;
  onPress: () => void;
  onClear?: () => void;
}) {
  return (
    <View style={[styles.chip, active ? styles.active : styles.idle]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={active ? `${label}, change filter` : `Filter by ${label}`}
        onPress={onPress}
        hitSlop={{ top: 6, bottom: 6 }}
        style={({ pressed }) => [styles.body, pressed && styles.pressed]}
      >
        {icon && <Icon name={icon} size={14} color={active ? colors.ink : colors.inkSoft} />}
        <Text variant="caption" tone={active ? "default" : "soft"} numberOfLines={1}>
          {label}
        </Text>
        {!(active && onClear) && (
          <Text variant="caption" tone="soft">
            ▾
          </Text>
        )}
      </Pressable>
      {active && onClear && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Remove filter: ${label}`}
          onPress={onClear}
          hitSlop={{ top: 6, bottom: 6, right: 6 }}
          style={({ pressed }) => [styles.clear, pressed && styles.pressed]}
        >
          <Icon name="close" size={14} color={colors.inkSoft} />
        </Pressable>
      )}
    </View>
  );
}

/** A small on/off filter, for one-tap questions ("Pending", "Over $100"). */
export function ToggleChip({ label, on, onToggle }: { label: string; on: boolean; onToggle: () => void }) {
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityState={{ checked: on }}
      onPress={onToggle}
      style={({ pressed }) => [styles.toggle, on ? styles.toggleOn : styles.toggleOff, pressed && styles.pressed]}
    >
      <Text variant="meta" tone={on ? "default" : "soft"}>
        {label}
      </Text>
    </Pressable>
  );
}

/** Clears every filter at once; shown first in a chip row while anything is filtered. */
export function ResetChip({ onPress }: { onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Reset all filters"
      onPress={onPress}
      hitSlop={{ top: 6, bottom: 6 }}
      style={({ pressed }) => [styles.reset, pressed && styles.pressed]}
    >
      <Icon name="refresh" size={14} color={colors.ink} />
      <Text variant="caption">Reset</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: { flexDirection: "row", alignItems: "center", minHeight: 36, borderRadius: radius.pill, borderWidth: 1 },
  idle: { borderColor: colors.lineStrong },
  active: { borderColor: colors.accent, backgroundColor: colors.accentWash },
  body: { flexDirection: "row", alignItems: "center", gap: 6, paddingLeft: space.md, paddingRight: space.md, minHeight: 36 },
  clear: { minHeight: 36, justifyContent: "center", paddingRight: space.md, marginLeft: -space.xs },
  pressed: { opacity: 0.6 },
  reset: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    minHeight: 36,
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    backgroundColor: colors.raised,
  },
  toggle: { minHeight: 32, justifyContent: "center", paddingHorizontal: space.sm + 2, borderRadius: radius.sm, borderWidth: 1 },
  toggleOn: { borderColor: colors.accent, backgroundColor: colors.accentWash },
  toggleOff: { borderColor: colors.line, backgroundColor: colors.surface },
});
