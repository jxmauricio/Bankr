import { GlassView, isGlassEffectAPIAvailable, isLiquidGlassAvailable } from "expo-glass-effect";
import { router, usePathname } from "expo-router";
import { TabList, TabSlot, Tabs, TabTrigger, type TabTriggerSlotProps } from "expo-router/ui";
import { createContext, use, useEffect, useState, type ReactNode, type Ref } from "react";
import { Pressable, StyleSheet, useWindowDimensions, View } from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, { cancelAnimation, Easing, useAnimatedStyle, useSharedValue, withTiming, type SharedValue } from "react-native-reanimated";
import { scheduleOnRN } from "react-native-worklets";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { useMoney } from "@/features/money/MoneyContext";
import { useNotifications } from "@/features/notifications/NotificationsContext";
import { ThemeToggle } from "@/theme/ThemeToggle";
import { radius, space } from "@/theme/tokens";
import { makeStyles, useColors, useScheme } from "@/theme/theme";
import { Icon, IconButton, Text, type IconName } from "@/ui";

/**
 * Five views, Chat in the middle: Home, Cash flow, Chat, Transactions, Plan.
 * Settings, a light/dark toggle and one action up top; a floating Liquid
 * Glass tab bar along the bottom. Swiping slides to the next tab.
 */
export default function TabsLayout() {
  const styles = useStyles();
  const focused = useOpenTab();

  return (
    <Tabs style={styles.root}>
      <SafeAreaView edges={["top"]} style={styles.header}>
        <TopBar onChat={focused === 2} />
      </SafeAreaView>
      <View style={styles.stage}>
        <SwipeBetweenTabs focused={focused} />
        <FloatingTabBar />
      </View>
      {/* Declares the routes; the icons above are what's shown. Tabs only reads triggers from a TabList that is its direct child. */}
      <TabList style={styles.hidden}>
        {TABS.map((t) => (
          <TabTrigger key={t.name} name={t.name} href={t.href} />
        ))}
      </TabList>
    </Tabs>
  );
}

const TABS = [
  { name: "index", href: "/", label: "Home", icon: "home" },
  { name: "cash-flow", href: "/cash-flow", label: "Cash flow", icon: "flow" },
  { name: "chat", href: "/chat", label: "Chat", icon: "chat" },
  { name: "transactions", href: "/transactions", label: "Transactions", icon: "list" },
  { name: "plan", href: "/plan", label: "Plan", icon: "calendar" },
] as const satisfies readonly { name: string; href: string; label: string; icon: IconName }[];

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

/**
 * Settings and light/dark on the left; notifications, then chat history on
 * the Chat tab or sync from the bank elsewhere, on the right.
 */
function TopBar({ onChat }: { onChat: boolean }) {
  const styles = useStyles();
  const { syncFromBank, isSyncing } = useMoney();
  const { unreadCount } = useNotifications();
  return (
    <View style={styles.bar}>
      <View style={styles.side}>
        <IconButton icon="settings" label="Accounts and goals" variant="plain" onPress={() => router.push("/money")} />
        <ThemeToggle />
      </View>
      <Text variant="brand" accessibilityRole="header">
        Bankr
      </Text>
      <View style={styles.side}>
        <View>
          <IconButton
            icon="bell"
            label={unreadCount ? `Notifications, ${unreadCount} unread` : "Notifications"}
            variant="plain"
            onPress={() => router.push("/notifications")}
          />
          {unreadCount > 0 && <View style={styles.dot} pointerEvents="none" />}
        </View>
        {onChat ? (
          // A new chat starts from the history sheet's "New chat" row.
          <IconButton icon="chat" label="Chat history" variant="plain" onPress={() => router.push("/history")} />
        ) : (
          <IconButton icon="refresh" label="Sync from bank" variant="plain" onPress={syncFromBank} loading={isSyncing} />
        )}
      </View>
    </View>
  );
}

/** Overlayed on the pages so the island floats; taps in the empty margin pass through. */
function FloatingTabBar() {
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const scheme = useScheme();
  const glass = isLiquidGlassAvailable() && isGlassEffectAPIAvailable();
  const tabs = TABS.map((t) => (
    <TabTrigger key={t.name} name={t.name} asChild>
      <TabIcon icon={t.icon} label={t.label} emphasized={t.name === "chat"} />
    </TabTrigger>
  ));
  return (
    <View pointerEvents="box-none" style={[styles.tabBarWrap, { paddingBottom: Math.max(insets.bottom, space.sm) }]}>
      {glass ? (
        <GlassView isInteractive glassEffectStyle="regular" colorScheme={scheme} style={styles.tabBar}>
          {tabs}
        </GlassView>
      ) : (
        <View style={[styles.tabBar, styles.tabBarSolid]}>{tabs}</View>
      )}
    </View>
  );
}

function TabIcon({
  icon,
  label,
  emphasized,
  isFocused,
  ref,
  ...props
}: TabTriggerSlotProps & { icon: IconName; label: string; emphasized?: boolean; ref?: Ref<View> }) {
  const styles = useStyles();
  const colors = useColors();
  // Chat sits in the middle with a green well so it reads as the main action.
  const well = emphasized ? (isFocused ? styles.tabIconChatOn : styles.tabIconChat) : isFocused ? styles.tabIconOn : null;
  const iconColor = emphasized ? (isFocused ? colors.onAccent : colors.accent) : isFocused ? colors.ink : colors.inkFaint;
  return (
    <Pressable
      ref={ref}
      {...props}
      accessibilityRole="tab"
      accessibilityLabel={label}
      accessibilityState={{ selected: isFocused }}
      style={({ pressed }) => [styles.tab, pressed && !isFocused && styles.pressed]}
    >
      <View style={[styles.tabIcon, well]}>
        <Icon name={icon} color={iconColor} size={18} />
      </View>
      <Text variant="tab" tone={emphasized ? "accent" : isFocused ? "default" : "faint"} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.75}>
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
    side: { flexDirection: "row", width: 88 },
    dot: {
      position: "absolute",
      top: 9,
      right: 9,
      width: 10,
      height: 10,
      borderRadius: 5,
      backgroundColor: colors.accent,
      borderWidth: 2,
      borderColor: colors.bg,
    },
    pager: { flex: 1, overflow: "hidden" },
    stage: { flex: 1 },
    hidden: { display: "none" },
    tabBarWrap: {
      position: "absolute",
      left: 0,
      right: 0,
      bottom: 0,
      // Inset more than the page cards (space.lg) so the island doesn't share their edges.
      paddingHorizontal: space.xl,
    },
    tabBar: {
      flexDirection: "row",
      flexGrow: 0,
      flexShrink: 0,
      borderRadius: radius.lg + 8,
      paddingVertical: 6,
      paddingHorizontal: 4,
      overflow: "hidden",
    },
    tabBarSolid: {
      backgroundColor: colors.surface,
      borderColor: colors.line,
      borderWidth: StyleSheet.hairlineWidth,
      shadowColor: colors.ink,
      shadowOpacity: 0.12,
      shadowRadius: 16,
      shadowOffset: { width: 0, height: 6 },
      elevation: 8,
    },
    tab: { flex: 1, minHeight: 52, alignItems: "center", justifyContent: "center", gap: 4 },
    tabIcon: { height: 26, width: 44, borderRadius: 13, alignItems: "center", justifyContent: "center" },
    tabIconOn: { backgroundColor: colors.raised },
    tabIconChat: { backgroundColor: colors.accentWash },
    tabIconChatOn: { backgroundColor: colors.accent },
    pressed: { opacity: 0.6 },
  })
);
