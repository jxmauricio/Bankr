import { ActivityIndicator, StyleSheet, View } from "react-native";
import { colors, space } from "@/theme/tokens";
import { Button } from "./Button";
import { Text } from "./Text";

export function Loading() {
  return (
    <View style={styles.center}>
      <ActivityIndicator color={colors.accent} />
    </View>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <View style={styles.center}>
      <Text tone="soft" align="center">
        {message}
      </Text>
      {onRetry && <Button label="Retry" variant="secondary" onPress={onRetry} />}
    </View>
  );
}

/** Stand-in for a view that hasn't been built for mobile yet. */
export function ComingSoon({ title, detail }: { title: string; detail: string }) {
  return (
    <View style={styles.center}>
      <Text variant="heading">{title}</Text>
      <Text tone="soft" align="center">
        {detail}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: space.md, padding: space.xl },
});
