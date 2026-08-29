import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { type MessageKey } from "./en";
import {
  LOCALES,
  LOCALE_STORAGE_KEY,
  readStoredLocale,
  setActiveLocale,
  type Locale,
} from "./locale";
import { translate, type Vars } from "./translate";

export type { Locale, MessageKey };
export { LOCALES };

type TranslateFn = (key: MessageKey, vars?: Vars) => string;

type I18nValue = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: TranslateFn;
};

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    const l = readStoredLocale();
    setActiveLocale(l);
    return l;
  });

  const setLocale = useCallback((l: Locale) => {
    setActiveLocale(l);
    setLocaleState(l);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, l);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    setActiveLocale(locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<I18nValue>(
    () => ({
      locale,
      setLocale,
      t: (key, vars) => translate(locale, key, vars),
    }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within <I18nProvider>");
  return ctx;
}

export function useT(): TranslateFn {
  return useI18n().t;
}

export function useLocale(): [Locale, (l: Locale) => void] {
  const { locale, setLocale } = useI18n();
  return [locale, setLocale];
}
