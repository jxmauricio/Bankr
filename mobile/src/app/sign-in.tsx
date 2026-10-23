import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, View } from "react-native";
import { ApiError, login, signUp } from "@/lib/api";
import { useSession } from "@/lib/session";
import { space } from "@/theme/tokens";
import { Button, Screen, Text, TextField } from "@/ui";

export default function SignInScreen() {
  const { signIn } = useSession();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const isSignup = mode === "signup";

  async function submit() {
    setError(null);
    setIsBusy(true);
    try {
      const response = isSignup ? await signUp(email.trim(), password, inviteCode.trim()) : await login(email.trim(), password);
      signIn(response.session_token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach Bankr. Check your connection.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <Screen edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.fill}>
        <View style={styles.hero}>
          <Text variant="title" tone="accent">
            bankr_
          </Text>
          <Text variant="display">Ask your money anything.</Text>
          <Text tone="soft">Check every answer.</Text>
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
            autoComplete={isSignup ? "new-password" : "current-password"}
            textContentType={isSignup ? "newPassword" : "password"}
          />
          {isSignup && (
            <TextField label="Invite code" value={inviteCode} onChangeText={setInviteCode} autoCapitalize="none" />
          )}
          {error && (
            <Text variant="caption" tone="negative" accessibilityRole="alert">
              {error}
            </Text>
          )}
          <Button label={isSignup ? "Create account" : "Sign in"} onPress={submit} loading={isBusy} />
          <Pressable onPress={() => setMode(isSignup ? "login" : "signup")} style={styles.switch}>
            <Text variant="caption" tone="soft" align="center">
              {isSignup ? "Have an account? Sign in" : "New here? Create an account"}
            </Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, justifyContent: "space-between" },
  hero: { gap: space.sm, paddingTop: space.xxl },
  form: { gap: space.md },
  switch: { paddingVertical: space.sm },
});
