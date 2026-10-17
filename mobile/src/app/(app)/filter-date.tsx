import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { useTransactionFilters } from "@/features/transactions/FiltersContext";
import { DATE_PRESETS, iso, parseIso, rangeLabel, windowRange } from "@/features/transactions/filtering";
import { RangeCalendar } from "@/features/transactions/RangeCalendar";
import { colors, radius, space } from "@/theme/tokens";
import { Button, Sheet, Text } from "@/ui";

type Draft = { preset: string | "custom"; start: string | null; end: string | null };

/**
 * Presets first, a range calendar for anything else. Nothing changes until
 * "Show transactions"; closing the sheet keeps the old dates.
 */
export default function DateFilterSheet() {
  const { filters, update } = useTransactionFilters();
  const today = iso(new Date());

  const [draft, setDraft] = useState<Draft>(() => {
    const d = filters.date;
    if (d.kind === "custom") return { preset: "custom", start: d.start, end: d.end };
    return { preset: d.window, ...windowRange(d.window) };
  });
  // The second tap of a custom range sets its end.
  const [picking, setPicking] = useState(false);
  const [month, setMonth] = useState(() => parseIso(draft.end ?? today));

  function pickPreset(window: string) {
    const range = windowRange(window);
    setDraft({ preset: window, ...range });
    setMonth(parseIso(range.end));
    setPicking(false);
  }

  function pickDay(day: string) {
    if (!picking || !draft.start) {
      setDraft({ preset: "custom", start: day, end: null });
      setPicking(true);
      return;
    }
    const [start, end] = day < draft.start ? [day, draft.start] : [draft.start, day];
    setDraft({ preset: "custom", start, end });
    setPicking(false);
  }

  function apply() {
    if (draft.preset !== "custom") update({ date: { kind: "preset", window: draft.preset } });
    else if (draft.start) update({ date: { kind: "custom", start: draft.start, end: draft.end ?? draft.start } });
    router.back();
  }

  const label = draft.start ? rangeLabel(draft.start, draft.end ?? draft.start) : "Pick a start date";

  return (
    <Sheet
      title="Date"
      trailing={
        <Text variant="moneySmall" tone="soft">
          {label}
        </Text>
      }
      footer={
        <View style={styles.actions}>
          <View style={styles.reset}>
            <Button label="Reset" variant="secondary" onPress={() => pickPreset("this_month")} />
          </View>
          <View style={styles.apply}>
            <Button label="Show transactions" onPress={apply} disabled={!draft.start} />
          </View>
        </View>
      }
    >
      <View accessibilityRole="radiogroup" accessibilityLabel="Date presets" style={styles.presets}>
        {[...DATE_PRESETS, { window: "custom", label: "Custom range" }].map((p) => {
          const on = draft.preset === p.window;
          return (
            <Pressable
              key={p.window}
              accessibilityRole="radio"
              accessibilityState={{ checked: on }}
              onPress={() => (p.window === "custom" ? (setDraft({ preset: "custom", start: null, end: null }), setPicking(true)) : pickPreset(p.window))}
              style={[styles.preset, on ? styles.presetOn : styles.presetOff]}
            >
              <Text variant="caption" tone={on ? "default" : "soft"}>
                {p.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <RangeCalendar month={month} onMonthChange={setMonth} start={draft.start} end={draft.end} today={today} onPick={pickDay} />
      <Text variant="meta" tone="faint">
        {picking ? "Now tap the last day." : "Tap a day to start a custom range."}
      </Text>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  presets: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  preset: {
    width: "48.5%",
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: space.md,
    borderRadius: radius.md - 2,
    borderWidth: 1,
  },
  presetOn: { borderColor: colors.accent, backgroundColor: colors.accentWash },
  presetOff: { borderColor: colors.line, backgroundColor: colors.surface },
  actions: { flexDirection: "row", gap: space.sm },
  reset: { flex: 1 },
  apply: { flex: 2 },
});
