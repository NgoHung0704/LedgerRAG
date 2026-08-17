import { de } from "@/messages/de";
import { en, type MessageKey } from "@/messages/en";
import { es } from "@/messages/es";
import { fr } from "@/messages/fr";
import { vi } from "@/messages/vi";

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
