import { de } from "@/messages/de";
import { en, type MessageKey } from "@/messages/en";
import { es } from "@/messages/es";
import { fr } from "@/messages/fr";
import { vi } from "@/messages/vi";

/** Where the choice is kept.
 *
 *  Declared HERE, in a plain module, and not in the provider that uses it: a
 *  Server Component importing a constant from a "use client" file receives a
 *  client reference rather than the string, so `cookies().get(NAME)` silently
 *  matched nothing and every request rendered the default. The cookie name is
 *  shared data, not part of a component. */
export const LOCALE_COOKIE = "locale";

export type Locale = "en" | "fr" | "vi" | "es" | "de";

export const LOCALES: { code: Locale; label: string }[] = [
  { code: "en", label: "English" },
  { code: "fr", label: "Français" },
  { code: "vi", label: "Tiếng Việt" },
  { code: "es", label: "Español" },
  { code: "de", label: "Deutsch" },
];

export const DEFAULT_LOCALE: Locale = "en";

export const catalogues: Record<Locale, Record<MessageKey, string>> = {
  en,
  fr,
  vi,
  es,
  de,
};

export function isLocale(value: string | undefined): value is Locale {
  return !!value && value in catalogues;
}

/** A key `t()` will accept: any real key, plus the BASE of a plural pair.
 *
 *  `verify.checked_one` and `verify.checked_other` are what the catalogues
 *  hold; `t("verify.checked", { count })` is what a caller writes, and the base
 *  exists in no catalogue. Derived from the `_other` members rather than listed
 *  by hand, so a plural added later is accepted without anyone remembering to
 *  widen this. TypeScript found this the moment the first plural was used —
 *  the alternative was typing the parameter as `string`, which would have
 *  thrown away the guard that makes the whole catalogue safe. */
type PluralBase<K> = K extends `${infer Base}_other` ? Base : never;

export type TKey = MessageKey | PluralBase<MessageKey>;

export type Vars = Record<string, string | number>;

/** One string, in one language, with its variables filled in.
 *
 *  Plural handling is deliberately only one/other: measured across every
 *  reader-facing string in this app there are exactly two plurals, and none of
 *  the five languages here needs more than that distinction. */
export function translate(
  catalogue: Record<string, string>,
  key: string,
  vars?: Vars,
): string {
  const source = en as Record<string, string>;
  const pluralKey =
    vars && typeof vars.count === "number"
      ? `${key}_${vars.count === 1 ? "one" : "other"}`
      : null;
  const template =
    (pluralKey ? catalogue[pluralKey] ?? source[pluralKey] : undefined) ??
    catalogue[key] ??
    source[key] ??
    key;
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    vars && name in vars ? String(vars[name]) : whole,
  );
}
