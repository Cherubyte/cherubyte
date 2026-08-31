// A tiny module-level mirror of the active locale so non-React helpers
// (lib/format.ts date + relative-time formatting) can localise without a hook.
// The I18nProvider keeps this in sync via setActiveLocale().

export type Locale = "en" | "pt";

export const LOCALES: Record<Locale, string> = {
  en: "English",
  pt: "Português",
};

export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_STORAGE_KEY = "cherubyte-locale";

let active: Locale = DEFAULT_LOCALE;

export function getActiveLocale(): Locale {
  return active;
}

export function setActiveLocale(l: Locale): void {
  active = l;
}

/** BCP-47 tag for Intl / toLocaleString APIs. */
export function intlLocale(): string {
  return active === "pt" ? "pt-PT" : "en-GB";
}

export function readStoredLocale(): Locale {
  try {
    const s = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (s === "en" || s === "pt") return s;
  } catch {
    /* private mode / disabled storage */
  }
  return DEFAULT_LOCALE;
}
