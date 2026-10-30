import { useSafeAreaInsets } from "react-native-safe-area-context";
import { space } from "./tokens";

/** The floating pill: inner padding plus the 52pt tab hit targets. */
export const FLOATING_TAB_BAR_HEIGHT = 64;

/**
 * Space to leave at the bottom of a tab screen so content and the composer
 * sit above the overlayed island (and the home indicator under it).
 */
export function useFloatingTabInset(): number {
  const insets = useSafeAreaInsets();
  return insets.bottom + FLOATING_TAB_BAR_HEIGHT + space.sm;
}
