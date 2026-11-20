import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { useTone } from "@/theme/theme";
import { type as typeScale } from "@/theme/tokens";
import { Text, type TextProps } from "./Text";

/** centsio — the s gets a tiny rectangle on its top and bottom. */
export function Wordmark({ variant = "title", tone = "accent", style }: Omit<TextProps, "children">) {
  const color = useTone(tone);
  const size = Number(typeScale[variant].fontSize) || 22;
  const markW = Math.max(2, Math.round(size * 0.12));
  const markH = Math.max(2, Math.round(size * 0.12));
  const [box, setBox] = useState({ width: 0, height: 0 });

  return (
    <View accessible accessibilityRole="header" accessibilityLabel="Centsio" style={[styles.row, style]}>
      <Text variant={variant} tone={tone}>
        cent
      </Text>
      <View>
        <Text variant={variant} tone={tone} onLayout={(e) => setBox(e.nativeEvent.layout)}>
          s
        </Text>
        {box.height > 0 ? (
          <>
            <View
              pointerEvents="none"
              style={{
                position: "absolute",
                left: box.width / 2 - markW / 2,
                top: box.height * 0.37 - markH + 1,
                width: markW,
                height: markH,
                backgroundColor: color,
              }}
            />
            <View
              pointerEvents="none"
              style={{
                position: "absolute",
                left: box.width / 2 - markW / 2,
                top: box.height * 0.82 - 1,
                width: markW,
                height: markH,
                backgroundColor: color,
              }}
            />
          </>
        ) : null}
      </View>
      <Text variant={variant} tone={tone}>
        io
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "baseline" },
});
