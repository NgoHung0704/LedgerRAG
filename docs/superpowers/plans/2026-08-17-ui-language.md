# UI Language Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a reader switch the application's own text between English, French, Vietnamese, Spanish and German, without changing the language the assistant answers in.

**Architecture:** A flat, typed message catalogue per language (`frontend/messages/*.ts`) with English as the source of truth, so a missing translation is a `tsc` error rather than a runtime surprise. A pure `translate()` function does `{name}` interpolation and a one/other plural choice. The active locale lives in a cookie so the Next.js server renders the first paint in the right language; a `LocaleProvider` hands it to a `useT()` hook, and a picker on the navigation rail beside `ThemeToggle` writes the cookie.

**Tech Stack:** Next.js 14 App Router, React 18, TypeScript (strict), Tailwind. New: `vitest` as a frontend dev dependency — the frontend has no test runner today.

**Spec:** `docs/superpowers/specs/2026-08-17-ui-language-design.md`

## Global Constraints

- **Five locales, exactly:** `en`, `fr`, `vi`, `es`, `de`. **Default `en`.**
- **English is the source of truth.** `messages/en.ts` is declared `as const`; the other four are `Record<MessageKey, string>`. Never widen those types — the compile error is the guard.
- **No prompt changes.** Nothing under `tablerag/` that builds a model prompt may be touched. The assistant keeps answering in the language of the documents. Any task that finds itself editing `tablerag/query/steps/generate.py` has gone out of scope — stop and report.
- **Reader-facing screens only.** In scope: `Sidebar.tsx`, `AppShell.tsx`, `ChatPanel.tsx`, `app/page.tsx`, `app/kb/[id]/page.tsx`, `ChatScopeSelector.tsx`, `SourceModal.tsx`, `CopyButton.tsx`, `ui.tsx`, `app/ask/page.tsx`. **Out of scope, stays English:** `app/doc/[docId]`, `ElementEditor.tsx`, `DocumentsPanel.tsx`, `app/models`, `app/audit`, `app/diagnostics`, `KbSettings.tsx`, assistants screens.
- **Key naming:** `<area>.<thing>`, lower snake inside the parts — `nav.knowledge_bases`, `chat.placeholder`, `caution.figure_reading`. Plurals add `_one` / `_other` to the key.
- **Spanish and German are unreviewed.** `messages/es.ts` and `messages/de.ts` each begin with a comment saying no native speaker has checked the register. Do not remove it.
- **Vietnamese does not mark plurals.** Its `_one` and `_other` values are identical on purpose. That is not a placeholder.
- **`kb.config.locale` is the NUMBER locale.** It is unrelated to this work. Do not read it, do not write it, do not rename it.
- Run `cd frontend && npx tsc --noEmit` after every task. Run `python -m pytest tests/unit -q` after any task that touches a `.tsx` file the Python guards read.

---

### Task 1: The catalogue, the lookup, and a test runner for the frontend

**Files:**
- Create: `frontend/messages/en.ts`, `frontend/messages/fr.ts`, `frontend/messages/vi.ts`, `frontend/messages/es.ts`, `frontend/messages/de.ts`
- Create: `frontend/lib/i18n.ts`
- Create: `frontend/lib/i18n.test.ts`
- Create: `frontend/vitest.config.ts`
- Modify: `frontend/package.json` (devDependency + `test` script)
- Modify: `README.md` (one line recording that es/de are unreviewed)
- Modify: `Makefile` (a `frontend-test` target)

**Interfaces:**
- Consumes: nothing.
- Produces: `type MessageKey`, `const en`, `const fr`, `const vi`, `const es`, `const de` (all `Record<MessageKey, string>` except `en` which is `as const`); `type Locale = "en" | "fr" | "vi" | "es" | "de"`; `const catalogues: Record<Locale, Record<MessageKey, string>>`; `function translate(catalogue: Record<string, string>, key: string, vars?: Vars): string`; `type Vars = Record<string, string | number>`.

- [ ] **Step 1: Install vitest and add the script**

```bash
cd frontend && npm install --save-dev vitest
```

Then in `frontend/package.json`, add to `"scripts"`:

```json
    "test": "vitest run"
```

- [ ] **Step 2: Create `frontend/vitest.config.ts`**

```ts
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// The i18n module imports through the "@/" alias that Next resolves from
// tsconfig paths; vitest has to be told about it separately.
const here = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: { alias: { "@": here } },
  // node, not jsdom: what is tested here is a pure function. useT() is a
  // three-line wrapper over it and a browser environment would be weight
  // carried for nothing.
  test: { environment: "node", include: ["lib/**/*.test.ts"] },
});
```

- [ ] **Step 3: Create `frontend/messages/en.ts` with the keys this task needs**

Only the four keys the tests use. Later tasks add the rest.

```ts
/** The source of truth. Every other catalogue is typed against this one, so a
 *  key added here breaks the build until all four translations exist — which is
 *  the point: with ~96 keys the real risk is rot, not the first pass. */
export const en = {
  "app.language": "Language",
  "source.header": "Source {index}: {filename}, page {page}",
  "verify.checked_one": "{count} number checked against sources",
  "verify.checked_other": "{count} numbers checked against sources",
} as const;

export type MessageKey = keyof typeof en;
```

- [ ] **Step 4: Create the four translations**

`frontend/messages/fr.ts`:

```ts
import type { MessageKey } from "@/messages/en";

export const fr: Record<MessageKey, string> = {
  "app.language": "Langue",
  "source.header": "Source {index} : {filename}, page {page}",
  "verify.checked_one": "{count} chiffre vérifié dans les sources",
  "verify.checked_other": "{count} chiffres vérifiés dans les sources",
};
```

`frontend/messages/vi.ts`:

```ts
import type { MessageKey } from "@/messages/en";

// Vietnamese does not mark plural number. The _one and _other forms below are
// identical on purpose — that is the language, not an unfinished translation.
export const vi: Record<MessageKey, string> = {
  "app.language": "Ngôn ngữ",
  "source.header": "Nguồn {index}: {filename}, trang {page}",
  "verify.checked_one": "Đã đối chiếu {count} con số với nguồn",
  "verify.checked_other": "Đã đối chiếu {count} con số với nguồn",
};
```

`frontend/messages/es.ts`:

```ts
import type { MessageKey } from "@/messages/en";

// NOT REVIEWED BY A NATIVE SPEAKER. Correct in meaning, unverified in register
// for an HR audience. Have a Spanish speaker read this file before relying on
// it in front of users, and delete this notice when they have.
export const es: Record<MessageKey, string> = {
  "app.language": "Idioma",
  "source.header": "Fuente {index}: {filename}, página {page}",
  "verify.checked_one": "{count} cifra verificada con las fuentes",
  "verify.checked_other": "{count} cifras verificadas con las fuentes",
};
```

`frontend/messages/de.ts`:

```ts
import type { MessageKey } from "@/messages/en";

// NOT REVIEWED BY A NATIVE SPEAKER. Correct in meaning, unverified in register
// for an HR audience. Have a German speaker read this file before relying on
// it in front of users, and delete this notice when they have.
export const de: Record<MessageKey, string> = {
  "app.language": "Sprache",
  "source.header": "Quelle {index}: {filename}, Seite {page}",
  "verify.checked_one": "{count} Zahl mit den Quellen abgeglichen",
  "verify.checked_other": "{count} Zahlen mit den Quellen abgeglichen",
};
```

- [ ] **Step 5: Write the failing tests**

Create `frontend/lib/i18n.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { de } from "@/messages/de";
import { en } from "@/messages/en";
import { fr } from "@/messages/fr";
import { translate } from "./i18n";

describe("translate", () => {
  it("returns the string for a plain key", () => {
    expect(translate(fr, "app.language")).toBe("Langue");
  });

  it("substitutes named variables", () => {
    expect(
      translate(en, "source.header", { index: 2, filename: "notice.pdf", page: 4 }),
    ).toBe("Source 2: notice.pdf, page 4");
  });

  it("leaves an unsupplied placeholder visible rather than blank", () => {
    // a silently empty gap in a sentence reads as a bug in the document, not
    // in the app; the braces make it obvious where to look
    expect(translate(en, "source.header", { index: 2 })).toContain("{filename}");
  });

  it("picks the singular form for a count of one", () => {
    expect(translate(fr, "verify.checked", { count: 1 })).toBe(
      "1 chiffre vérifié dans les sources",
    );
  });

  it("picks the plural form for any other count", () => {
    expect(translate(fr, "verify.checked", { count: 7 })).toBe(
      "7 chiffres vérifiés dans les sources",
    );
    expect(translate(de, "verify.checked", { count: 0 })).toBe(
      "0 Zahlen mit den Quellen abgeglichen",
    );
  });

  it("uses the base key when a count is given but no plural forms exist", () => {
    expect(translate(en, "app.language", { count: 3 })).toBe("Language");
  });

  it("falls back to English when the catalogue is missing the key", () => {
    // typed callers cannot reach this; it is here so a hand-edited catalogue
    // degrades to a readable English word instead of a blank
    const gappy = { ...fr } as Record<string, string>;
    delete gappy["app.language"];
    expect(translate(gappy, "app.language")).toBe("Language");
  });

  it("returns the key itself when nothing knows it", () => {
    expect(translate(fr, "nope.not_a_key")).toBe("nope.not_a_key");
  });
});
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run`
Expected: FAIL — `Failed to resolve import "./i18n"`.

- [ ] **Step 7: Write `frontend/lib/i18n.ts`**

```ts
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
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run`
Expected: PASS, 8 tests.

- [ ] **Step 9: Prove the type guard actually guards**

Temporarily delete the `"app.language"` line from `frontend/messages/de.ts`, then run:

Run: `cd frontend && npx tsc --noEmit`
Expected: FAIL — `Property '"app.language"' is missing in type ... but required in type 'Record<MessageKey, string>'`.

Restore the line and re-run; expected: clean. **Do not skip this step.** The compile-time guard is the whole reason the catalogue is typed this way, and a guard nobody has seen fail is a guard nobody knows works.

- [ ] **Step 10: Add the Makefile target and the README note**

In `Makefile`, add `frontend-test` to the `.PHONY` list and add the target next to `docs-test`:

```make
# ---- frontend unit tests (message catalogue + i18n lookup) -----------------
frontend-test:
	cd frontend && npx vitest run
```

In `README.md`, add one line to the section that lists the eval/test commands:

```markdown
`make frontend-test` runs the frontend unit tests (message catalogue, i18n
lookup). The Spanish and German catalogues are correct in meaning but have not
been read by a native speaker — `messages/es.ts` and `messages/de.ts` say so at
the top, and the notice stays until one has.
```

- [ ] **Step 11: Commit**

```bash
git add frontend/messages frontend/lib/i18n.ts frontend/lib/i18n.test.ts \
        frontend/vitest.config.ts frontend/package.json Makefile README.md
git commit -m "a missing translation should break the build, not the page"
```

---

### Task 2: The locale reaches the first paint

**Files:**
- Create: `frontend/components/LocaleProvider.tsx`
- Create: `frontend/components/LocaleToggle.tsx`
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/components/Sidebar.tsx:205` (mount the toggle beside `ThemeToggle`)

**Interfaces:**
- Consumes: `Locale`, `DEFAULT_LOCALE`, `LOCALES`, `catalogues`, `isLocale`, `translate` from Task 1.
- Produces: `<LocaleProvider locale={...}>`; `useT(): (key: MessageKey, vars?: Vars) => string`; `useLocale(): { locale: Locale; setLocale: (next: Locale) => void }`; cookie name `LOCALE_COOKIE = "locale"`.

- [ ] **Step 1: Create `frontend/components/LocaleProvider.tsx`**

```tsx
"use client";

import { createContext, useContext, useState } from "react";

import {
  catalogues,
  DEFAULT_LOCALE,
  translate,
  type Locale,
  type Vars,
} from "@/lib/i18n";
import type { MessageKey } from "@/messages/en";

export const LOCALE_COOKIE = "locale";

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
```

- [ ] **Step 2: Read the cookie in `frontend/app/layout.tsx`**

Add the imports:

```tsx
import { cookies } from "next/headers";

import { LocaleProvider, LOCALE_COOKIE } from "@/components/LocaleProvider";
import { DEFAULT_LOCALE, isLocale } from "@/lib/i18n";
```

Replace the body of `RootLayout` with:

```tsx
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // reading a cookie makes this route dynamic, which it already is: every page
  // in this app is behind auth and shows live data
  const saved = cookies().get(LOCALE_COOKIE)?.value;
  const locale = isLocale(saved) ? saved : DEFAULT_LOCALE;

  return (
    <html lang={locale} suppressHydrationWarning>
      <head>
        {/* apply the saved theme before first paint, so there's no flash */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('theme');if(t==='dark'||(!t&&matchMedia('(prefers-color-scheme:dark)').matches))document.documentElement.classList.add('dark')}catch(e){}",
          }}
        />
      </head>
      <body>
        <LocaleProvider locale={locale}>
          <AppShell>{children}</AppShell>
        </LocaleProvider>
      </body>
    </html>
  );
}
```

Note the `lang` attribute now follows the choice. It was hardcoded `"en"`, which was wrong for a screen reader on any page.

- [ ] **Step 3: Create `frontend/components/LocaleToggle.tsx`**

```tsx
"use client";

import { Languages } from "lucide-react";

import { useLocale } from "@/components/LocaleProvider";
import { LOCALES, type Locale } from "@/lib/i18n";

/** Language picker on the rail, styled against navy like ThemeToggle beside it.
 *
 *  A native <select> rather than a menu: it is five items, it must work with a
 *  keyboard and a screen reader, and the platform already does that properly. */
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
```

The option labels are each written in their own language and are **not** translated — a reader looking for their language recognises "Deutsch", not "German".

- [ ] **Step 4: Mount it in `frontend/components/Sidebar.tsx`**

Add the import beside the existing `ThemeToggle` import:

```tsx
import LocaleToggle from "@/components/LocaleToggle";
```

At line 205, beside `<ThemeToggle compact={collapsed} />`, add:

```tsx
          <LocaleToggle compact={collapsed} />
```

- [ ] **Step 5: Prove it end to end by translating one real string**

In `frontend/messages/en.ts` add `"nav.ask": "Ask",` and the four translations
(`fr` "Demander", `vi` "Hỏi", `es` "Preguntar", `de` "Fragen"). In
`Sidebar.tsx`, replace the hardcoded `"Ask"` nav label with `t("nav.ask")`,
adding `const t = useT();` at the top of the component.

- [ ] **Step 6: Check it in the browser**

Run: `cd frontend && npm run dev`, open `http://localhost:3000/ask`
Expected: the rail shows a language picker; choosing Français changes the "Ask" nav item to "Demander"; **reloading the page shows "Demander" immediately, with no flash of "Ask"**. That last part is what the cookie buys — if you see a flash, the layout is reading the cookie in the wrong place.

- [ ] **Step 7: Typecheck and run the suites**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: both clean.
Run: `python -m pytest tests/unit -q`
Expected: 1028 passed, 2 xfailed (unchanged — no Python touched).

- [ ] **Step 8: Commit**

```bash
git add frontend/components/LocaleProvider.tsx frontend/components/LocaleToggle.tsx \
        frontend/app/layout.tsx frontend/components/Sidebar.tsx frontend/messages
git commit -m "the server has to know the language, or the first paint is wrong"
```

---

### Task 3: Translate the shell

**Files:**
- Modify: `frontend/components/Sidebar.tsx` (~16 strings), `frontend/components/AppShell.tsx`
- Modify: `frontend/messages/en.ts` + the four translations

**Interfaces:**
- Consumes: `useT()` from Task 2.
- Produces: keys under the `nav.` prefix.

- [ ] **Step 1: List the strings**

Run: `cd frontend && grep -oE '"[A-Z][^"]{2,}"' components/Sidebar.tsx components/AppShell.tsx`

Expect: `Assistants`, `Ask` (already done in Task 2), `Knowledge Bases`, `Model Providers`, `Audit log`, `Diagnostics`, `LedgerRAG — home`, `Close navigation`, `Main`, `Admin`, `User`, `Expand the navigation rail`, `Collapse the navigation rail`, `Expand`, `Collapse`.

`"Escape"` is a **keyboard key name**, not prose — leave it alone.

- [ ] **Step 2: Add the keys to all five catalogues**

Worked example for three of them; do the rest the same way.

`en.ts`:

```ts
  "nav.knowledge_bases": "Knowledge Bases",
  "nav.model_providers": "Model Providers",
  "nav.collapse_rail": "Collapse the navigation rail",
```

`fr.ts`:

```ts
  "nav.knowledge_bases": "Bases de connaissances",
  "nav.model_providers": "Fournisseurs de modèles",
  "nav.collapse_rail": "Réduire la barre de navigation",
```

`vi.ts`:

```ts
  "nav.knowledge_bases": "Kho tri thức",
  "nav.model_providers": "Nhà cung cấp mô hình",
  "nav.collapse_rail": "Thu gọn thanh điều hướng",
```

`es.ts`:

```ts
  "nav.knowledge_bases": "Bases de conocimiento",
  "nav.model_providers": "Proveedores de modelos",
  "nav.collapse_rail": "Contraer la barra de navegación",
```

`de.ts`:

```ts
  "nav.knowledge_bases": "Wissensdatenbanken",
  "nav.model_providers": "Modellanbieter",
  "nav.collapse_rail": "Navigationsleiste einklappen",
```

- [ ] **Step 3: Replace the literals with `t(...)`**

Add `const t = useT();` inside each component and swap every listed literal for its key. `aria-label` and `title` attributes are user-facing too — translate them.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean. A key you added to `en.ts` and forgot in one translation fails here, by design.

- [ ] **Step 5: Check in the browser**

Run: `npm run dev`, switch to each of the five languages in turn.
Expected: every rail label changes; nothing renders as a raw key like `nav.audit_log`.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/Sidebar.tsx frontend/components/AppShell.tsx frontend/messages
git commit -m "the shell speaks the reader's language too"
```

---

### Task 4: Translate the chat, and take the French out of the code

**Files:**
- Modify: `frontend/components/ChatPanel.tsx` (~24 English + ~15 hardcoded French)
- Modify: `frontend/messages/*.ts`
- Create: `tests/unit/test_ui_language.py`

**Interfaces:**
- Consumes: `useT()` from Task 2.
- Produces: keys under `chat.`, `caution.`, `verify.`, `sources.`, `routing.`.

This is the task the whole thing exists for: `ChatPanel.tsx` is where the
application currently speaks French at readers who never asked it to.

- [ ] **Step 1: Move `CAUTION_COPY` into the catalogues**

The four reason keys — `figure_reading`, `low_confidence`, `needs_review`,
`unverified_numbers` — become `caution.figure_reading` and so on. **Keep the
pipeline's machine keys exactly as they are**; only the copy moves. Replace the
`CAUTION_COPY` object with a lookup through `t()`:

```tsx
const lines = caution.reasons
  .map((reason) => CAUTION_KEYS[reason])
  .filter(Boolean)
  .map((key) => t(key));
```

where `CAUTION_KEYS: Record<string, MessageKey>` maps machine key to message
key. An unknown reason still yields nothing, which is what
`test_every_caution_reason_has_copy_in_the_ui` in
`tests/unit/test_chat_caution_stream.py` guards — **that test reads
`CAUTION_COPY` by name and will break.** Update it in the same commit to read
`CAUTION_KEYS` instead, and keep it asserting the same thing: every reason the
Python can emit has copy behind it.

- [ ] **Step 2: Translate the rest of the panel**

Including: the composer placeholder, the empty-state prompts, `Copy the
question` / `Copy the answer`, `Ask this again`, the `Source {index}: ...`
title, `+{hidden} more`, `needs review`, the see-also row's label and its
`Sur ces pages, non lu par l'assistant :` sentence, the routing badge's
`Unsure — searched all {count} knowledge bases` (a plural: `_one` / `_other`),
and `{count} number(s) checked against sources` (the other plural).

- [ ] **Step 3: Write the failing guard**

Create `tests/unit/test_ui_language.py`:

```python
"""No screen in the reader's path may speak a language nobody chose.

The application used to be English with about fifteen French strings around the
answer — I wrote those, reasoning that the reader is a CETIAT employee. The
reasoning was right about the reader and wrong about the result: the app spoke
two languages at once and no user had picked either.

Accented characters are the test, which catches French, Spanish and German but
NOT an unaccented French sentence ("Vous pouvez consulter le document"). It is a
tripwire for the common case, not a proof. The proof is that every string in
these files goes through t().
"""

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# the reader-facing screens, per the design. Operator screens are out of scope
# and stay English.
TRANSLATED = [
    "frontend/components/Sidebar.tsx",
    "frontend/components/AppShell.tsx",
    "frontend/components/ChatPanel.tsx",
    "frontend/components/ChatScopeSelector.tsx",
    "frontend/components/SourceModal.tsx",
    "frontend/components/CopyButton.tsx",
    "frontend/app/ask/page.tsx",
    "frontend/app/page.tsx",
    "frontend/app/kb/[id]/page.tsx",
]

_LITERAL_WITH_ACCENT = re.compile(
    r"""(["'])([^"'\n]*[àâäéèêëîïôöùûüçñßÀÂÄÉÈÊËÎÏÔÖÙÛÜÇÑ][^"'\n]*)\1""")


def test_no_translated_screen_carries_a_literal_in_another_language():
    offenders = {}
    for rel in TRANSLATED:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        hits = [m.group(2) for m in
                _LITERAL_WITH_ACCENT.finditer(path.read_text(encoding="utf-8"))]
        if hits:
            offenders[rel] = hits[:3]
    assert not offenders, (
        f"reader-facing screens still carry hardcoded copy: {offenders} — "
        f"move it into frontend/messages/ and call t()")
```

- [ ] **Step 4: Run it to verify it fails before the migration is finished**

Run: `python -m pytest tests/unit/test_ui_language.py -q`
Expected: FAIL, naming `ChatPanel.tsx` and the French strings still in it. If it
passes on the first run, the migration in Step 2 is already complete — check
that the file really is clean rather than that the regex is broken, by
temporarily re-adding one French literal and watching it go red.

- [ ] **Step 5: Finish the migration until it passes**

Run: `python -m pytest tests/unit/test_ui_language.py -q`
Expected: PASS.

- [ ] **Step 6: Run everything**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Run: `python -m pytest tests/unit -q`
Expected: all clean; the caution-copy guard updated in Step 1 still passes.

- [ ] **Step 7: Check in the browser**

Run: `npm run dev`, ask a question that produces a caution (any answer citing a
figure) in each of the five languages.
Expected: the caution notice, the verification badge and the see-also row all
follow the picker. **The answer itself stays in the document's language** — that
is the design, not a bug.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/ChatPanel.tsx frontend/messages \
        tests/unit/test_ui_language.py tests/unit/test_chat_caution_stream.py
git commit -m "the app spoke French at readers who never chose it"
```

---

### Task 5: Translate the knowledge-base screens

**Files:**
- Modify: `frontend/app/page.tsx` (~21 strings), `frontend/app/kb/[id]/page.tsx` (~4)
- Modify: `frontend/messages/*.ts`

**Interfaces:**
- Consumes: `useT()` from Task 2.
- Produces: keys under `kb.`.

- [ ] **Step 1: List the strings**

Run: `cd frontend && grep -oE '"[A-Z][^"]{3,}"|>[A-Z][^<>{}]{3,}<' app/page.tsx 'app/kb/[id]/page.tsx'`

- [ ] **Step 2: Add the keys to all five catalogues**

Worked example:

`en.ts`: `"kb.create": "New knowledge base",`
`fr.ts`: `"kb.create": "Nouvelle base de connaissances",`
`vi.ts`: `"kb.create": "Kho tri thức mới",`
`es.ts`: `"kb.create": "Nueva base de conocimiento",`
`de.ts`: `"kb.create": "Neue Wissensdatenbank",`

- [ ] **Step 3: Replace the literals with `t(...)`**

`app/page.tsx` is a client component already (it uses hooks); if either file is
a server component, `useT()` cannot be called there — convert only the piece
that renders text into a small client component rather than making the whole
page client.

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Run: `python -m pytest tests/unit/test_ui_language.py -q`
Expected: both clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/page.tsx 'frontend/app/kb/[id]/page.tsx' frontend/messages
git commit -m "the knowledge-base screens follow the picker"
```

---

### Task 6: Translate the remaining reader screens

**Files:**
- Modify: `frontend/components/ChatScopeSelector.tsx` (~7), `frontend/components/SourceModal.tsx` (~3), `frontend/components/CopyButton.tsx` (~2), `frontend/components/ui.tsx` (~3), `frontend/app/ask/page.tsx` (~1)
- Modify: `frontend/messages/*.ts`

**Interfaces:**
- Consumes: `useT()` from Task 2.
- Produces: keys under `scope.`, `source.`, `common.`.

- [ ] **Step 1: List the strings**

Run: `cd frontend && grep -oE '"[A-Z][^"]{3,}"|>[A-Z][^<>{}]{3,}<' components/ChatScopeSelector.tsx components/SourceModal.tsx components/CopyButton.tsx components/ui.tsx app/ask/page.tsx`

- [ ] **Step 2: Add the keys to all five catalogues, and replace the literals**

Worked example for the one in `app/ask/page.tsx`:

`en.ts`: `"scope.search_in": "Search in",`
`fr.ts`: `"scope.search_in": "Chercher dans",`
`vi.ts`: `"scope.search_in": "Tìm trong",`
`es.ts`: `"scope.search_in": "Buscar en",`
`de.ts`: `"scope.search_in": "Suchen in",`

`ui.tsx` holds shared primitives used by operator screens too. Translate only
the strings reached from a reader screen; if a string is used by both, translate
it — an operator reading "Fermer" on a button is a far smaller problem than a
reader reading "Close" in the middle of French.

- [ ] **Step 3: Verify the whole thing**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Run: `python -m pytest tests/unit -q`
Run: `cd frontend && npm run build`
Expected: all clean. The production build is checked here because `cookies()` in
the root layout opts every route into dynamic rendering, and this is the moment
to see that it did not break the build.

- [ ] **Step 4: Walk the reader's whole path in each language**

Run: `npm run dev`. In each of the five languages: open `/ask`, pick a scope,
ask a question, open a source, copy an answer.
Expected: no raw key on screen, no English left in a non-English run, no layout
broken by a longer German word.

- [ ] **Step 5: Commit**

```bash
git add frontend/components frontend/app frontend/messages
git commit -m "every screen on the reader's path now follows the picker"
```

---

## Self-review notes

Checked against the spec section by section:

- *Decisions 1–4* — Global Constraints, verbatim.
- *Typed catalogue as the guard* — Task 1 Steps 3–4, **proven by Step 9**, which
  requires seeing the compile error rather than trusting it.
- *Lookup: interpolation, one/other, English fallback* — Task 1 Steps 5–7, one
  test each, including the two negative cases (unsupplied variable, unknown key).
- *Cookie, not localStorage* — Task 2 Steps 1–2, with the no-flash reload check
  as an explicit expected result in Step 6.
- *`<html lang>` from the cookie* — Task 2 Step 2.
- *Scope: the ten reader-facing files* — Tasks 3–6 cover all ten; the Python
  guard in Task 4 lists the same ten, so a file dropped from the migration is
  caught rather than forgotten.
- *es/de unreviewed* — Task 1 Step 4 (file headers) and Step 10 (README).
- *Vietnamese plural forms identical* — Task 1 Step 4, with the reason in a
  comment so a later reader does not "fix" it.
- *vitest* — Task 1 Steps 1–2, 8, wired into the Makefile in Step 10.
- *Out of scope* — no task touches `tablerag/`, except the Python guard file in
  Task 4 (a test, no prompt) and the caution-copy guard it must update.

One known limit, stated rather than hidden: the Python guard tests for **accented
characters**, so an unaccented French sentence would slip past it. It is a
tripwire for the common case. The real assurance is `tsc` plus the browser walk
in Task 6 Step 4.
