import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useMemo } from "react";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SessionProvider, useSession } from "@/lib/session";
import { usePushNotifications } from "@/features/notifications/usePush";
import { restoreAppearance } from "@/theme/appearance";
import { useColors, useScheme } from "@/theme/theme";

restoreAppearance();

export default function RootLayout() {
  const scheme = useScheme();
  const colors = useColors();
  const navTheme = useMemo(() => {
    const base = scheme === "light" ? DefaultTheme : DarkTheme;
    return {
      ...base,
      colors: { ...base.colors, background: colors.bg, card: colors.bg, primary: colors.accent, text: colors.ink, border: colors.line },
    };
  }, [scheme, colors]);

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
  usePushNotifications();
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
