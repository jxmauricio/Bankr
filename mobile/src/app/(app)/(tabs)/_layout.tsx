import { router, usePathname } from "expo-router";
import { TabList, TabSlot, Tabs, TabTrigger, type TabTriggerSlotProps } from "expo-router/ui";
import { createContext, use, useEffect, useRef, type Ref } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useMoney } from "@/features/money/MoneyContext";
import { colors, radius, space } from "@/theme/tokens";
import { IconButton, Text } from "@/ui";

/**
 * The same five views as the web app's ViewTabBar, as a top bar: settings,
 * the app's name and one action, over a row of pill tabs that scrolls
 * sideways and keeps the open tab in view.
 */
export default function TabsLayout() {
  const scroller = useRef<ScrollView>(null);
  const reveal = (x: number) => scroller.current?.scrollTo({ x: Math.max(0, x - space.xl), animated: true });

  return (
    <RevealContext value={reveal}>
      <Tabs style={styles.root}>
        <SafeAreaView edges={["top"]} style={styles.header}>
          <TopBar />
        </SafeAreaView>
        <ScrollView
          ref={scroller}
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.tabs}
          contentContainerStyle={styles.tabsContent}
        >
          {TABS.map((t) => (
            <TabTrigger key={t.name} name={t.name} asChild>
              <TabPill label={t.label} />
            </TabTrigger>
          ))}
        </ScrollView>
        <TabSlot />
        {/* Declares the routes; the pills above are what's shown. Tabs only reads triggers from a TabList that is its direct child. */}
        <TabList style={styles.hidden}>
          {TABS.map((t) => (
            <TabTrigger key={t.name} name={t.name} href={t.href} />
          ))}
        </TabList>
      </Tabs>
    </RevealContext>
  );
}

const TABS = [
  { name: "index", href: "/", label: "Chat" },
  { name: "transactions", href: "/transactions", label: "Transactions" },
  { name: "cash-flow", href: "/cash-flow", label: "Cash flow" },
  { name: "health", href: "/health", label: "Health" },
  { name: "plan", href: "/plan", label: "Plan" },
] as const;

/** Settings on the left; chat history on the Chat tab, otherwise sync from the bank. */
function TopBar() {
  const { syncFromBank, isSyncing } = useMoney();
  const onChat = usePathname() === "/";
  return (
    <View style={styles.bar}>
      <IconButton icon="settings" label="Accounts and goals" variant="plain" onPress={() => router.push("/money")} />
      <Text variant="brand" accessibilityRole="header">
        Bankr
      </Text>
      {onChat ? (
        // A new chat starts from the history sheet's "New chat" row.
        <IconButton icon="chat" label="Chat history" variant="plain" onPress={() => router.push("/history")} />
      ) : (
        <IconButton icon="refresh" label="Sync from bank" variant="plain" onPress={syncFromBank} disabled={isSyncing} />
      )}
    </View>
  );
}

/** Scrolls the tab row so a tab at this x is in view. */
const RevealContext = createContext<(x: number) => void>(() => {});

function TabPill({ label, isFocused, ref, ...props }: TabTriggerSlotProps & { label: string; ref?: Ref<View> }) {
  const reveal = use(RevealContext);
  const x = useRef(0);
  useEffect(() => {
    if (isFocused) reveal(x.current);
  }, [isFocused, reveal]);

  return (
    <Pressable
      ref={ref}
      {...props}
      accessibilityRole="tab"
      accessibilityState={{ selected: isFocused }}
      onLayout={(e) => {
        x.current = e.nativeEvent.layout.x;
        if (isFocused) reveal(x.current);
      }}
      style={({ pressed }) => [styles.pill, isFocused && styles.pillOn, pressed && !isFocused && styles.pressed]}
    >
      <Text variant="tab" tone={isFocused ? "onAccent" : "soft"}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  header: { backgroundColor: colors.bg },
  bar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: space.sm + 2 },
  tabs: { flexGrow: 0, flexShrink: 0 },
  hidden: { display: "none" },
  tabsContent: { gap: space.xs, paddingHorizontal: space.lg, paddingTop: space.sm + 2, paddingBottom: space.sm },
  pill: { height: 34, justifyContent: "center", paddingHorizontal: space.md + 2, borderRadius: radius.pill },
  pillOn: { backgroundColor: colors.accent },
  pressed: { opacity: 0.6 },
});
