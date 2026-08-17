"use client";

import { Languages } from "lucide-react";

import { useLocale } from "@/components/LocaleProvider";
import { LOCALES, type Locale } from "@/lib/i18n";

/** Language picker on the rail, styled against navy like ThemeToggle beside it.
 *
 *  A native <select> rather than a menu: it is five items, it must work with a
 *  keyboard and a screen reader, and the platform already does that properly.
 *
 *  The option labels are each written in their own language and are NOT
 *  translated — someone looking for their language scans for "Deutsch", not for
 *  whatever the current interface language calls German. */
export default function LocaleToggle({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale } = useLocale();
  const active = LOCALES.find((l) => l.code === locale);

  return (
    <label
      className={`inline-flex items-center gap-2 rounded-md border border-rail-line text-[12px] font-medium text-rail-ink transition-colors hover:border-indigo-400 hover:text-indigo-300 ${
        compact ? "h-8 w-8 justify-center" : "px-2.5 py-1.5"
      }`}
      title={active ? active.label : "Language"}
    >
      <Languages size={14} aria-hidden="true" />
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        aria-label="Language"
        className={`cursor-pointer bg-transparent outline-none ${
          compact ? "sr-only" : ""
        }`}
      >
        {LOCALES.map((l) => (
          <option key={l.code} value={l.code} className="text-ink">
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}
