import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";
import { space } from "@/theme/tokens";
import { Button, Screen, Text, Wordmark } from "@/ui";

/** Logged-out landing: questionnaire first, or the existing login. */
export default function WelcomeScreen() {
  const router = useRouter();
  return (
    <Screen edges={["top", "bottom"]}>
      <View style={styles.hero}>
        <Wordmark />
        <Text variant="display">Ask your money anything.</Text>
        <Text tone="soft">Check every answer.</Text>
      </View>
      <View style={styles.footer}>
        <Button label="Get started" onPress={() => router.push("/onboard")} />
        <Button label="Log in" variant="secondary" onPress={() => router.push("/sign-in")} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { flex: 1, justifyContent: "center", gap: space.sm },
  footer: { gap: space.sm },
});
