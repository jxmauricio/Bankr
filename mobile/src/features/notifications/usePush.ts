import { useEffect } from "react";
import { Platform } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { registerPushToken } from "@/lib/api";
import { useSession } from "@/lib/session";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

type OpenHandler = (target: string) => void;

let pendingTarget: string | null = null;
const openHandlers = new Set<OpenHandler>();

/** Home calls this once the screens a push opens are actually on the stack. */
export function consumePendingOpen(): string | null {
  const target = pendingTarget;
  pendingTarget = null;
  return target;
}

export function subscribePushOpen(handler: OpenHandler): () => void {
  openHandlers.add(handler);
  return () => {
    openHandlers.delete(handler);
  };
}

function openTarget(target: string) {
  if (openHandlers.size > 0) {
    openHandlers.forEach((handler) => handler(target));
    pendingTarget = null;
  } else {
    pendingTarget = target;
  }
}

/** Where a tapped push leads: its week's recap, or the notifications list for a daily briefing. */
function targetFromResponse(response: Notifications.NotificationResponse | null | undefined): string | null {
  if (!response || response.actionIdentifier !== Notifications.DEFAULT_ACTION_IDENTIFIER) return null;
  const data = response.notification.request.content.data;
  const trigger = response.notification.request.trigger;
  const payload =
    trigger && typeof trigger === "object" && "payload" in trigger
      ? (trigger as Notifications.PushNotificationTrigger).payload
      : undefined;
  for (const bag of [data, payload]) {
    if (!bag || typeof bag !== "object") continue;
    const record = bag as Record<string, unknown>;
    const week = record.week_start ?? record.weekStart;
    if (typeof week === "string" && week.length > 0) return `/recap/${week}`;
    if (record.type === "daily_briefing") return "/notifications";
  }
  if (data && typeof data === "object" && (data as { type?: unknown }).type === "weekly_recap") {
    return "/recap/latest";
  }
  return null;
}

/**
 * Ask for notification permission on launch (so a Simulator banner can
 * show), register the APNs token after sign-in (phones only — the
 * Simulator has none), and open the recap or the daily briefing's
 * notifications list when they tap a push.
 */
export function usePushNotifications() {
  const { token } = useSession();
  const lastResponse = Notifications.useLastNotificationResponse();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (Platform.OS === "android") {
        await Notifications.setNotificationChannelAsync("default", {
          name: "Bankr",
          importance: Notifications.AndroidImportance.DEFAULT,
        });
      }
      const before = await Notifications.getPermissionsAsync();
      const { status } = await Notifications.requestPermissionsAsync();
      if (cancelled || status !== "granted") return;

      // Simulator never gets real APNs. The first time they Allow, show the
      // same weekly recap banner the Sunday cron will send to a phone.
      if (__DEV__ && !Device.isDevice && before.status !== "granted") {
        await Notifications.scheduleNotificationAsync({
          content: {
            title: "Your weekly recap is ready",
            body: "Sep 7–13: $198.45 more went out than came in. Spent $238.45, 62% under usual.",
            data: { type: "weekly_recap", week_start: "latest" },
          },
          trigger: { type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL, seconds: 2 },
        });
      }

      if (!token || !Device.isDevice) return;
      try {
        const device = await Notifications.getDevicePushTokenAsync();
        const value = typeof device.data === "string" ? device.data : null;
        if (value) await registerPushToken(token, value, Platform.OS === "android" ? "android" : "ios");
      } catch {
        // No APNs token (Simulator, or a build without the push entitlement).
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    const target = targetFromResponse(lastResponse);
    if (target) openTarget(target);
  }, [lastResponse]);
}
