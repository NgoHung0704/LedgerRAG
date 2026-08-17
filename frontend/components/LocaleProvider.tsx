"use client";

import { createContext, useContext, useState } from "react";

import {
  catalogues,
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  translate,
  type Locale,
  type Vars,
} from "@/lib/i18n";
import type { MessageKey } from "@/messages/en";

type Ctx = { locale: Locale; setLocale: (next: Locale) => void };

const LocaleContext = createContext<Ctx>({
  locale: DEFAULT_LOCALE,
  setLocale: () => {},
});

/** The active language, seeded by the SERVER from the cookie.
 *
 *  Seeded rather than read here on purpose: a language is content, not a CSS
 *  class, so reading it in the browser would paint English first and swap on
 *  every navigation — and React would warn about the hydration mismatch while
 *  it did. The cookie is readable by the server layout, so the first paint is
 *  already right. */
export function LocaleProvider({
  locale: initial,
  children,
}: {
  locale: Locale;
  children: React.ReactNode;
}) {
  const [locale, setLocaleState] = useState<Locale>(initial);

  const setLocale = (next: Locale) => {
    setLocaleState(next);
    document.documentElement.lang = next;
    // a year, path-wide, SameSite=Lax: it is a display preference, it never
    // travels cross-site, and it must survive a closed browser
    document.cookie = `${LOCALE_COOKIE}=${next};path=/;max-age=31536000;SameSite=Lax`;
  };

  return (
    <LocaleContext.Provider value={{ locale, setLocale }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale() {
  return useContext(LocaleContext);
}

export function useT() {
  const { locale } = useContext(LocaleContext);
  return (key: MessageKey, vars?: Vars) =>
    translate(catalogues[locale], key, vars);
}
