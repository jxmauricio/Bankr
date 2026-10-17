import { NativeTabs } from "expo-router/unstable-native-tabs";
import { colors } from "@/theme/tokens";

/** The same five views as the web app's ViewTabBar, as a native tab bar. */
export default function TabsLayout() {
  return (
    <NativeTabs tintColor={colors.accent} backgroundColor={colors.bg} labelStyle={{ color: colors.inkFaint }}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Label>Chat</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf={{ default: "bubble.left", selected: "bubble.left.fill" }} md="chat" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="transactions">
        <NativeTabs.Trigger.Label>Transactions</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="list.bullet" md="list" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="cash-flow">
        <NativeTabs.Trigger.Label>Cash flow</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="arrow.triangle.branch" md="account_tree" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="health">
        <NativeTabs.Trigger.Label>Health</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="waveform.path.ecg" md="monitor_heart" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="plan">
        <NativeTabs.Trigger.Label>Plan</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="calendar" md="calendar_month" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
