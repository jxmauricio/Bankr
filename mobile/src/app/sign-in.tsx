import { useRouter } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, View } from "react-native";
import { ApiError, login } from "@/lib/api";
import { useSession } from "@/lib/session";
import { space } from "@/theme/tokens";
import { Button, Screen, Text, TextField, Wordmark } from "@/ui";

export default function SignInScreen() {
  const router = useRouter();
  const { signIn } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  async function submit() {
    setError(null);
    setIsBusy(true);
    try {
      const response = await login(email.trim(), password);
      signIn(response.session_token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach Centsio. Check your connection.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <Screen edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.fill}>
        <View style={styles.hero}>
          <Wordmark />
          <Text variant="display">Log in.</Text>
          <Text tone="soft">Welcome back.</Text>
        </View>

        <View style={styles.form}>
          <TextField
            label="Email"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            textContentType="emailAddress"
            placeholder="you@example.com"
          />
          <TextField
            label="Password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="current-password"
            textContentType="password"
          />
          {error && (
            <Text variant="caption" tone="negative" accessibilityRole="alert">
              {error}
            </Text>
          )}
          <Button label="Sign in" onPress={submit} loading={isBusy} />
          <Button label="Back" variant="ghost" onPress={() => router.replace("/")} />
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, justifyContent: "space-between" },
  hero: { gap: space.sm, paddingTop: space.xxl },
  form: { gap: space.md },
});
