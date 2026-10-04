import { messages, type Locale, type MessageKey } from "./messages";

export type { Locale, MessageKey } from "./messages";
export { locales, messages } from "./messages";

const STORAGE_KEY = "filmroll-locale";

function detectLocale(): Locale {
  if (typeof window === "undefined") return "en";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved === "en" || saved === "es" || saved === "fr") return saved;

  const lang = navigator.language.toLowerCase();
  if (lang.startsWith("es")) return "es";
  if (lang.startsWith("fr")) return "fr";
  return "en";
}

// An external store rather than component state: the server has no way to know
// the guest's locale, so the client reads it during hydration instead.
let current: Locale | null = null;
const listeners = new Set<() => void>();

export function subscribeLocale(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

export function getLocale(): Locale {
  current ??= detectLocale();
  return current;
}

export function getServerLocale(): Locale {
  return "en";
}

export function setStoredLocale(locale: Locale): void {
  if (current === locale) return;
  current = locale;
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // Private mode can reject writes; the choice still applies to this session.
  }
  listeners.forEach((listener) => listener());
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
