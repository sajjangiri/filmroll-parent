import AsyncStorage from "@react-native-async-storage/async-storage";

import { messages, type Locale, type MessageKey } from "./messages";

export type { Locale, MessageKey } from "./messages";
export { locales, messages } from "./messages";

const STORAGE_KEY = "filmroll-locale";

function deviceLocale(): Locale {
  const lang = Intl.DateTimeFormat().resolvedOptions().locale.toLowerCase();
  if (lang.startsWith("es")) return "es";
  if (lang.startsWith("fr")) return "fr";
  return "en";
}

export async function detectLocale(): Promise<Locale> {
  const saved = await AsyncStorage.getItem(STORAGE_KEY);
  if (saved === "en" || saved === "es" || saved === "fr") return saved;
  return deviceLocale();
}

export async function saveLocale(locale: Locale): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEY, locale);
}

export function translate(
  locale: Locale,
  key: MessageKey,
  vars?: Record<string, string | number>,
): string {
  let text = messages[locale][key] ?? messages.en[key];
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}
