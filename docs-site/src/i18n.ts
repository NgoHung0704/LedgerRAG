import type { Lang } from "./route";

/** A localized string is a pair. There is no third state, and no fallback:
 *  a missing half is a guard failure in tests/unit/test_docs_content.py, not
 *  something the UI papers over at runtime. */
export type L = { vi: string; en: string };

export const pick = (value: L, lang: Lang): string => value[lang];

export const other = (lang: Lang): Lang => (lang === "vi" ? "en" : "vi");
