"use client";

import { locales } from "@/lib/i18n";
import { useI18n } from "@/components/guest/I18nProvider";

export function LanguagePicker() {
  const { locale, setLocale, t } = useI18n();

  return (
    <div className="flex items-center gap-1 self-end" role="group" aria-label={t("language")}>
      {locales.map(({ code, label }) => (
        <button
          key={code}
          type="button"
          onClick={() => setLocale(code)}
          aria-label={label}
          className={
            locale === code
              ? "inline-flex min-h-11 min-w-11 items-center justify-center rounded-full bg-zinc-800 text-sm font-medium text-white"
              : "inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-sm text-zinc-400"
          }
          aria-pressed={locale === code}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
