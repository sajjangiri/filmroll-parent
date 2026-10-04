/**
 * Guest reveal notifications.
 *
 * Hosts already get email. Guests who joined from this app can opt in to a
 * push when the film develops. Instant films skip the ask: they are born
 * developed, so "your film is ready" would fire as the host hits create.
 *
 * Expo Go on SDK 57 often cannot mint a remote token. Registration then no-ops
 * rather than blocking join — a development or App Store build is what actually
 * delivers. The API still stores whatever token we do get.
 */

import { Platform } from "react-native";
import * as Notifications from "expo-notifications";

import { registerPushToken } from "./api/client";
import type { Locale } from "./i18n";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export function filmCodeFromNotificationData(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const record = data as { code?: unknown; url?: unknown };
  if (typeof record.code === "string" && /^[A-Za-z0-9]{4,12}$/.test(record.code)) {
    return record.code.toUpperCase();
  }
  if (typeof record.url === "string") {
    const match = record.url.match(/\/f\/([A-Za-z0-9]{4,12})(?:[/?#]|$)/i);
    if (match) return match[1].toUpperCase();
  }
  return null;
}

export async function registerGuestPush(
  code: string,
  guestToken: string,
  locale: Locale,
): Promise<void> {
  try {
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "Filmroll",
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    }

    const existing = await Notifications.getPermissionsAsync();
    let status = existing.status;
    if (status !== "granted") {
      const asked = await Notifications.requestPermissionsAsync();
      status = asked.status;
    }
    if (status !== "granted") return;

    const expo = await Notifications.getExpoPushTokenAsync();
    if (!expo.data) return;
    await registerPushToken(code, guestToken, expo.data, locale);
  } catch {
    // Simulator, Expo Go without a project id, or a denied prompt. Joining
    // still has to work; the gallery is the fallback.
  }
}
