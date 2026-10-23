import { router, usePathname } from "expo-router";
import { TabList, TabSlot, Tabs, TabTrigger, type TabTriggerSlotProps } from "expo-router/ui";
import { createContext, use, useEffect, useRef, useState, type ReactNode, type Ref } from "react";
import { Pressable, ScrollView, StyleSheet, useWindowDimensions, View } from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, { cancelAnimation, Easing, useAnimatedStyle, useSharedValue, withTiming, type SharedValue } from "react-native-reanimated";
import { scheduleOnRN } from "react-native-worklets";
import { SafeAreaView } from "react-native-safe-area-context";
import { useMoney } from "@/features/money/MoneyContext";
import { radius, space } from "@/theme/tokens";
import { makeStyles } from "@/theme/theme";
import { IconButton, Text } from "@/ui";

/**
 * The same five views as the web app's ViewTabBar, as a top bar: settings,
 * the app's name and one action, over a row of pill tabs that scrolls
 * sideways and keeps the open tab in view. Swiping the page sideways slides
 * to the next or previous tab.
 */
export default function TabsLayout() {
  const styles = useStyles();
  const scroller = useRef<ScrollView>(null);
  const reveal = (x: number) => scroller.current?.scrollTo({ x: Math.max(0, x - space.xl), animated: true });
  const focused = useOpenTab();

  return (
    <RevealContext value={reveal}>
      <Tabs style={styles.root}>
        <SafeAreaView edges={["top"]} style={styles.header}>
          <TopBar onChat={focused === 0} />
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
        <SwipeBetweenTabs focused={focused} />
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

/**
 * The open tab's place in TABS. A sheet over the tabs (accounts, chat
 * history, a filter) has its own path, so this keeps the last tab while one
 * is open instead of falling back to the first.
 */
function useOpenTab() {
  const pathname = usePathname();
  const [open, setOpen] = useState(() => Math.max(0, TABS.findIndex((t) => t.href === pathname)));
  const onTab = TABS.findIndex((t) => t.href === pathname);
  if (onTab !== -1 && onTab !== open) setOpen(onTab);
  return onTab === -1 ? open : onTab;
}

/** How a page settles after a swipe or a tap on a neighbouring pill. */
const SETTLE = { duration: 260, easing: Easing.out(Easing.cubic) };

/** Where the pager is, in pages (1.5 is halfway between the second and third tab). */
const PagerContext = createContext<{ position: SharedValue<number>; width: number; focused: number } | null>(null);

/**
 * Lays the tabs side by side and drags them with your finger: right to left
 * brings in the next tab, left to right the previous one, and letting go
 * past halfway (or with a flick) settles on it. The focused tab's neighbours
 * stay rendered so they're already there mid-swipe. Only a clearly sideways
 * drag counts, so vertical scrolling is untouched; the horizontal chip rows
 * use gesture-handler's ScrollView so they scroll instead of paging.
 */
function SwipeBetweenTabs({ focused }: { focused: number }) {
  const styles = useStyles();
  const { width } = useWindowDimensions();
  const position = useSharedValue(focused);
  const start = useSharedValue(focused);
  // The tab a swipe just settled on (-1 for none), so its navigation doesn't animate again.
  const swipedTo = useSharedValue(-1);

  // A pill tap: slide to a neighbouring tab, jump straight to a far one.
  useEffect(() => {
    const swiped = swipedTo.get() === focused;
    swipedTo.set(-1);
    if (swiped) return;
    position.set(Math.abs(position.get() - focused) <= 1 ? withTiming(focused, SETTLE) : focused);
  }, [focused, position, swipedTo]);

  const last = TABS.length - 1;
  const pan = Gesture.Pan()
    .activeOffsetX([-20, 20])
    .failOffsetY([-12, 12])
    .onStart(() => {
      cancelAnimation(position);
      start.set(position.get());
    })
    .onUpdate(({ translationX }) => {
      const p = start.get() - translationX / width;
      // Resist past the first and last tab.
      position.set(p < 0 ? p * 0.3 : p > last ? last + (p - last) * 0.3 : p);
    })
    .onEnd(({ velocityX }) => {
      const from = Math.round(start.get());
      const projected = Math.round(position.get() - (velocityX / width) * 0.4);
      const to = Math.min(last, Math.max(0, from - 1, Math.min(from + 1, projected)));
      position.set(withTiming(to, SETTLE));
      if (to === from) return;
      swipedTo.set(to);
      scheduleOnRN(openTab, to);
    });

  return (
    <PagerContext value={{ position, width, focused }}>
      <GestureDetector gesture={pan}>
        <View style={styles.pager}>
          <TabSlot
            detachInactiveScreens={false}
            style={styles.pager}
            // Placed by the pill order; the navigator's own route order differs.
            renderFn={(descriptor, { loaded }) => (
              <Page index={TABS.findIndex((t) => t.name === descriptor.route.name)} loaded={loaded} render={descriptor.render} />
            )}
          />
        </View>
      </GestureDetector>
    </PagerContext>
  );
}

function openTab(index: number) {
  router.navigate(TABS[index].href);
}

/** One tab, placed by its distance from the pager's position. */
function Page({ index, loaded, render }: { index: number; loaded: boolean; render: () => ReactNode }) {
  const { position, width, focused } = use(PagerContext)!;
  const slide = useAnimatedStyle(() => ({ transform: [{ translateX: (index - position.get()) * width }] }));
  const isFocused = index === focused;
  if (!loaded && Math.abs(index - focused) > 1) return null;

  return (
    <Animated.View
      style={[StyleSheet.absoluteFill, slide, { pointerEvents: isFocused ? "auto" : "none" }]}
      accessibilityElementsHidden={!isFocused}
      importantForAccessibility={isFocused ? "auto" : "no-hide-descendants"}
    >
      {render()}
    </Animated.View>
  );
}

/** Settings on the left; chat history on the Chat tab, otherwise sync from the bank. */
function TopBar({ onChat }: { onChat: boolean }) {
  const styles = useStyles();
  const { syncFromBank, isSyncing } = useMoney();
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
  const styles = useStyles();
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

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.bg },
    header: { backgroundColor: colors.bg },
    bar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: space.sm + 2 },
    tabs: { flexGrow: 0, flexShrink: 0 },
    pager: { flex: 1, overflow: "hidden" },
    hidden: { display: "none" },
    tabsContent: { gap: space.xs, paddingHorizontal: space.lg, paddingTop: space.sm + 2, paddingBottom: space.sm },
    pill: { height: 34, justifyContent: "center", paddingHorizontal: space.md + 2, borderRadius: radius.pill },
    pillOn: { backgroundColor: colors.accent },
    pressed: { opacity: 0.6 },
  })
);
