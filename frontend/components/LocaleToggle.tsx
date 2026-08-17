"use client";

import { Languages } from "lucide-react";

import { useLocale } from "@/components/LocaleProvider";
import { LOCALES, type Locale } from "@/lib/i18n";

/** Language picker on the rail.
 *
 *  A native <select> rather than a menu: it is five items, it must work with a
 *  keyboard and a screen reader, and the platform already does that properly.
 *
 *  Two things about it are not decoration:
 *
 *  `color-scheme: dark` is why the option list is legible. The popup is painted
 *  by the browser, outside this stylesheet's reach — a `color` on <option> is
 *  advisory and several engines ignore it — so without this the list came back
 *  as grey-on-grey, every entry but the highlighted one barely readable. The
 *  rail is deep navy in BOTH page themes by design (globals.css), so declaring
 *  the control dark is a statement of fact here, not a guess about the theme.
 *
 *  Collapsed, the select covers the whole button at zero opacity instead of
 *  being `sr-only`: a hidden control cannot be clicked, and the icon would have
 *  been a button that does nothing.
 *
 *  The option labels are each written in their own language and are NOT
 *  translated — someone looking for their language scans for "Deutsch", not for
 *  whatever the current interface language calls German. */
export default function LocaleToggle({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale } = useLocale();
  const active = LOCALES.find((l) => l.code === locale);

  return (
    <label
      className={`relative inline-flex items-center gap-2 rounded-md border border-rail-line text-[12px] font-medium text-rail-hi transition-colors hover:border-indigo-400 hover:text-indigo-300 ${
        compact ? "h-8 w-8 justify-center" : "w-full px-2.5 py-1.5"
      }`}
      title={active ? active.label : "Language"}
    >
      <Languages size={14} aria-hidden="true" className="shrink-0" />
      {!compact && <span className="truncate">{active?.label}</span>}
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        aria-label="Language"
        style={{ colorScheme: "dark" }}
        className={
          compact
            ? "absolute inset-0 cursor-pointer opacity-0"
            : "absolute inset-0 w-full cursor-pointer opacity-0"
        }
      >
        {LOCALES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}
