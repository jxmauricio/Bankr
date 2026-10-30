import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { router, type Href } from "expo-router";
import { useEffect } from "react";
import { Platform } from "react-native";
import { registerPushDevice, removePushDevice } from "@/lib/api";

// A push that arrives while the app is open still shows as a banner.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

/**
 * The phone's Expo push token, asking for permission the first time. Null
 * when it can't have one: notifications denied, no EAS project id in the
 * app config (push needs one), or a device that can't receive pushes.
 */
async function expoPushToken(): Promise<string | null> {
  if (Platform.OS === "web" || !Device.isDevice) return null;
  if (Platform.OS === "android") {
    // Android 13+ only shows the permission prompt once a channel exists.
    await Notifications.setNotificationChannelAsync("default", {
      name: "Briefings and recaps",
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }
  let { status } = await Notifications.getPermissionsAsync();
  if (status === "undetermined") ({ status } = await Notifications.requestPermissionsAsync());
  if (status !== "granted") return null;

  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  if (!projectId) return null;
  return (await Notifications.getExpoPushTokenAsync({ projectId })).data;
}

/** Where a tapped push leads: the recap it announces, or the notifications list. */
function targetFor(data: Record<string, unknown> | undefined): Href {
  if (data?.kind === "weekly_recap" && typeof data.week_start === "string") return `/recap/${data.week_start}`;
  return "/notifications";
}

/**
 * While signed in: register this phone for pushes, open the right screen
 * when one is tapped, and unregister on sign out so the next account on
 * this phone doesn't get this one's news.
 */
export function usePushNotifications(token: string | null) {
  useEffect(() => {
    if (!token) return;
    let pushToken: string | null = null;
    let cancelled = false;
    expoPushToken()
      .then((t) => {
        if (cancelled || !t) return;
        pushToken = t;
        return registerPushDevice(token, t, Platform.OS === "ios" ? "ios" : "android");
      })
      // Offline or denied: the briefing and recap are still in the app; try again next launch.
      .catch(() => {});
    return () => {
      cancelled = true;
      if (pushToken) removePushDevice(token, pushToken).catch(() => {});
    };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    const open = (response: Notifications.NotificationResponse) =>
      router.push(targetFor(response.notification.request.content.data as Record<string, unknown> | undefined));
    // A tap that launched the app from closed.
    Notifications.getLastNotificationResponseAsync().then((response) => {
      if (!response) return;
      open(response);
      // Handled: a later launch from the home screen shouldn't open it again.
      Notifications.clearLastNotificationResponseAsync().catch(() => {});
    });
    const subscription = Notifications.addNotificationResponseReceivedListener(open);
    return () => subscription.remove();
  }, [token]);
}
