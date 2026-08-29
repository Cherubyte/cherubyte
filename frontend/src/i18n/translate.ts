import { en, type MessageKey } from "./en";
import { pt } from "./pt";
import { DEFAULT_LOCALE, getActiveLocale, type Locale } from "./locale";

export type { MessageKey };
export type Vars = Record<string, string | number>;

const DICTS: Record<Locale, Record<string, string>> = { en, pt };

export function translate(locale: Locale, key: MessageKey, vars?: Vars): string {
  let s = DICTS[locale][key] ?? DICTS[DEFAULT_LOCALE][key] ?? key;
  if (vars) {
    for (const name of Object.keys(vars)) {
      s = s.split(`{${name}}`).join(String(vars[name]));
    }
  }
  return s;
}

/** Non-hook translate for module-level helpers (lib/format.ts). */
export function tStatic(key: MessageKey, vars?: Vars): string {
  return translate(getActiveLocale(), key, vars);
}
