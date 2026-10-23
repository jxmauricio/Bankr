import { useColorScheme } from "react-native";
import { darkColors, lightColors, tones, type Colors, type Tone } from "./tokens";

export type Scheme = "light" | "dark";

const PALETTES: Record<Scheme, Colors> = { light: lightColors, dark: darkColors };

/** The system appearance; dark when the system doesn't say. */
export function useScheme(): Scheme {
  return useColorScheme() === "light" ? "light" : "dark";
}

/** The palette for the current appearance, for colors set inline or passed as props. */
export function useColors(): Colors {
  return PALETTES[useScheme()];
}

export function useTone(tone: Tone): string {
  return tones(useColors())[tone];
}

/**
 * A file's styles, built once per appearance from that appearance's palette:
 * `const useStyles = makeStyles((colors) => StyleSheet.create({...}))`, then
 * `const styles = useStyles()` inside the component.
 */
export function makeStyles<T>(factory: (colors: Colors) => T): () => T {
  const built: Partial<Record<Scheme, T>> = {};
  return function useStyles() {
    const scheme = useScheme();
    return (built[scheme] ??= factory(PALETTES[scheme]));
  };
}
