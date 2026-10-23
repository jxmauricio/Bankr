import { JetBrainsMono_400Regular, JetBrainsMono_500Medium } from "@expo-google-fonts/jetbrains-mono";
import {
  SpaceGrotesk_400Regular,
  SpaceGrotesk_500Medium,
  SpaceGrotesk_600SemiBold,
} from "@expo-google-fonts/space-grotesk";
import { useFonts } from "expo-font";
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect, useMemo } from "react";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SessionProvider, useSession } from "@/lib/session";
import { useColors, useScheme } from "@/theme/theme";

// Keep the splash up until the fonts are in, so text never renders in the
// system font first and then jumps.
SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({
    SpaceGrotesk_400Regular,
    SpaceGrotesk_500Medium,
    SpaceGrotesk_600SemiBold,
    JetBrainsMono_400Regular,
    JetBrainsMono_500Medium,
  });
  const ready = fontsLoaded || fontError !== null;

  const scheme = useScheme();
  const colors = useColors();
  const navTheme = useMemo(() => {
    const base = scheme === "light" ? DefaultTheme : DarkTheme;
    return {
      ...base,
      colors: { ...base.colors, background: colors.bg, card: colors.bg, primary: colors.accent, text: colors.ink, border: colors.line },
    };
  }, [scheme, colors]);

  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  // A font that fails to load falls back to the system font rather than blocking the app.
  if (!ready) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SessionProvider>
        <ThemeProvider value={navTheme}>
          <StatusBar style={scheme === "light" ? "dark" : "light"} />
          <RootStack />
        </ThemeProvider>
      </SessionProvider>
    </GestureHandlerRootView>
  );
}

/** Signed out sees only sign-in; signed in sees only the app. */
function RootStack() {
  const colors = useColors();
  const { isAuthenticated } = useSession();
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}>
      <Stack.Protected guard={!isAuthenticated}>
        <Stack.Screen name="sign-in" />
      </Stack.Protected>
      <Stack.Protected guard={isAuthenticated}>
        <Stack.Screen name="(app)" />
      </Stack.Protected>
    </Stack>
  );
}
