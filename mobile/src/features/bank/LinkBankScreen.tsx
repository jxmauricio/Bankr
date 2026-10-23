import { StyleSheet, View } from "react-native";
import { useSession } from "@/lib/session";
import { space } from "@/theme/tokens";
import { Button, Screen, Text } from "@/ui";
import { useLinkBank } from "./useLinkBank";

/** Onboarding's first step: no bank yet, so link one through Plaid. */
export function LinkBankScreen({ onLinked }: { onLinked: () => void }) {
  const { signOut } = useSession();
  const { link, busy, error } = useLinkBank(onLinked);

  return (
    <Screen edges={["top", "bottom"]}>
      <View style={styles.hero}>
        <Text variant="title" tone="accent">
          bankr_
        </Text>
        <Text variant="display">Link your bank.</Text>
        <Text tone="soft">
          Bankr reads your balances and transactions through Plaid, read-only. It can&apos;t move money, and you can disconnect any time.
        </Text>
      </View>
      <View style={styles.actions}>
        {error && (
          <Text variant="caption" tone="negative" accessibilityRole="alert">
            {error}
          </Text>
        )}
        <Button label="Link a bank" onPress={link} loading={busy} />
        <Button label="Sign out" variant="ghost" onPress={signOut} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { flex: 1, justifyContent: "center", gap: space.md },
  actions: { gap: space.sm },
});
