import * as SecureStore from "expo-secure-store";
import { useState } from "react";
import { Appearance } from "react-native";

/** The user's choice in settings: follow the system, or always light or dark. */
export type AppearancePref = "system" | "light" | "dark";

const STORAGE_KEY = "bankr_appearance";

function apply(pref: AppearancePref) {
  // Overrides what useColorScheme() reports app-wide; "unspecified" hands it back to the system.
  Appearance.setColorScheme(pref === "system" ? "unspecified" : pref);
}

function read(): AppearancePref {
  const saved = SecureStore.getItem(STORAGE_KEY);
  if (saved === "light" || saved === "dark" || saved === "system") return saved;
  return "light";
}

/** Applies the saved choice. Called once at launch, before the first frame, so a forced mode never flashes the other. */
export function restoreAppearance() {
  apply(read());
}

/** The saved choice and a setter that applies it at once and remembers it. */
export function useAppearancePref(): [AppearancePref, (pref: AppearancePref) => void] {
  const [pref, setPref] = useState(read);
  function choose(next: AppearancePref) {
    setPref(next);
    apply(next);
    SecureStore.setItemAsync(STORAGE_KEY, next).catch(() => {});
  }
  return [pref, choose];
}
