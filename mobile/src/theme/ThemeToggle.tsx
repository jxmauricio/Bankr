import { Pressable, StyleSheet } from "react-native";
import { radius } from "@/theme/tokens";
import { makeStyles, useColors, useScheme } from "@/theme/theme";
import { useAppearancePref } from "./appearance";
import { Icon } from "@/ui";

/** Sun/moon control for the top bar. Same toggle as the web app: light ↔ dark. */
export function ThemeToggle() {
  const styles = useStyles();
  const colors = useColors();
  const scheme = useScheme();
  const [, choose] = useAppearancePref();
  const toDark = scheme === "light";

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={toDark ? "Switch to dark mode" : "Switch to light mode"}
      onPress={() => choose(toDark ? "dark" : "light")}
      hitSlop={4}
      style={({ pressed }) => [styles.hit, pressed && styles.pressed]}
    >
      <Icon name={toDark ? "moon" : "sun"} color={colors.inkSoft} size={19} />
    </Pressable>
  );
}

const useStyles = makeStyles(() =>
  StyleSheet.create({
    hit: { width: 44, height: 44, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
    pressed: { opacity: 0.6 },
  })
);
