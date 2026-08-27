import type { Lang } from "./route";

/** A localized string is one value per language the page is written in.
 *  There is no fallback: a missing language is a guard failure in
 *  tests/unit/test_docs_content.py, not something the UI papers over. */
export type L = { vi: string; en: string; fr: string };

export const LANGS = ["en", "fr", "vi"] as const;

export const pick = (value: L, lang: Lang): string => value[lang];
