# UI language: five languages for the reader, English for the operator

Design agreed 2026-08-17. The application's own text becomes switchable between
five languages. What the assistant *answers* does not change, and neither does
any prompt.

## The problem

The interface is written in English, except for about fifteen French strings
around the answer — the caution notice, the verification badge, the see-also
row. I wrote those French strings myself over the last few sessions, on the
reasoning that the reader is a CETIAT employee. That reasoning is right about
the reader and wrong about the result: the application now speaks two languages
at once, and no user picked either of them.

Nothing in the repo helps. There is no i18n library, no locale context, and
`kb.config.locale` is not what its name suggests to a reader of this document:
its UI label is **"Number locale"**, and `core/numbers.py` uses it to decide
whether `4,79` is four-point-seven-nine. It also pins the language of *generated
summaries*. It has never had anything to do with the language of the interface.

## Decisions taken, and what each one closes off

| | decision | what it rules out |
|---|---|---|
| 1 | **The application's text only.** The assistant keeps answering in the language of the documents. | No change to `SYSTEM_PROMPT`, which is byte-identical to the measured configuration; every eval gate stays where it is. |
| 2 | **Five languages: English, French, Vietnamese, Spanish, German.** English is the default. | Matches the locales `core/numbers.py` already handles, plus Vietnamese. |
| 3 | **Reader-facing screens only.** Operator screens stay English. | `rowspan`, `records`, `reranker`, `needs_review` are not translated, because translating them makes them harder to read for the one person who reads them. |
| 4 | **An explicit picker, remembered on the machine.** No auto-detection, no server-side per-user preference. | A French office with an English Windows install would otherwise get English and not know why. |

Decision 2 carries a limit that belongs in the repo rather than in my head:
**Spanish and German have not been reviewed by a speaker.** They will be
correct in meaning and unverified in register. `messages/es.ts` and
`messages/de.ts` say so at the top of the file, and the README says so too.

## Mechanism

### The catalogue is typed, so a missing translation is a build error

`frontend/messages/en.ts` is the source of truth:

```ts
export const en = {
  "chat.placeholder": "Ask your question… (Enter to send, ↑ for an earlier one)",
  "source.header": "Source {index}: {filename}, page {page}",
  "verify.checked_one": "{count} number checked against sources",
  "verify.checked_other": "{count} numbers checked against sources",
} as const;

export type MessageKey = keyof typeof en;
```

The other four are declared `Record<MessageKey, string>`. A key missing from one
of them, or a key misspelled in one of them, **fails `tsc --noEmit`** — which
already runs. This replaces the runtime guard I would otherwise have written,
and it is strictly better: adding an English string breaks the build until all
four translations exist, so the catalogue cannot rot quietly. The rot is the
real risk here, not the first translation pass.

### Lookup

A `LocaleProvider` holds the active locale; `useT()` returns `t(key, vars?)`:

- `{name}` in the string is replaced from `vars.name`.
- when `vars.count` is given and `<key>_other` exists, `_one` is chosen for
  a count of 1 and `_other` otherwise. Vietnamese gives both forms the same
  text, which is what Vietnamese does — not a workaround.
- a key absent from the active catalogue falls back to English rather than
  rendering blank. This cannot happen through typed callers; it is there so a
  hand-edited catalogue degrades visibly instead of silently.

Measured before designing this: across every reader-facing string there are
**two** plurals (`{n} number(s) checked`, `knowledge base(s)`) and a handful of
interpolations. Nothing needs ordinal rules, gendered agreement, or date
formatting, which is why no library earns its place here.

### A cookie, not localStorage

This reverses what I proposed while asking the questions, and the reason is
worth writing down. `ThemeToggle` persists to `localStorage` and an inline
script in `layout.tsx` applies the class before first paint. That works because
a theme is **a CSS class**. A language is **content**: Next.js renders the HTML
on the server, which cannot read `localStorage`, so every page load would paint
English first and swap — a visible flash on every navigation for every non-
English reader, plus a hydration mismatch.

A cookie is readable by the server layout, so the first paint is already in the
right language. Same user-visible behaviour as agreed — explicit picker,
remembered on this machine, English by default — different place to keep it.

`<html lang>` is set from the same cookie. It is hardcoded today, which is
wrong for screen readers whatever language the page is in.

## Scope

**Translated** — the shell plus everything a reader touches to ask a question
and check a source. `/ask` carries the sidebar, so the shell is in scope: a
translated page inside an English frame is not a translated application.

| file | keys |
|---|---|
| `Sidebar.tsx`, `AppShell.tsx` | ~16 |
| `ChatPanel.tsx` incl. Bibliography, SeeAlsoRow, CautionNotice, VerificationBadge, RoutedBadge | ~24 + ~15 currently hardcoded French |
| `app/page.tsx`, `app/kb/[id]/page.tsx` | ~25 |
| `ChatScopeSelector`, `SourceModal`, `CopyButton`, `ui.tsx`, `app/ask` | ~16 |

≈ 96 keys × 5 languages ≈ 480 strings.

**Not translated:** `app/doc/[docId]` (47), `ElementEditor` (27),
`DocumentsPanel` (19), `app/models` (18), Audit, Diagnostics, `KbSettings`,
Assistants.

## Testing

| what | how | why there |
|---|---|---|
| every key exists in all five languages | `tsc --noEmit` | compile error, no test to run or forget |
| `t()` — interpolation, one/other, unknown key falls back | **vitest, new to the frontend** | there is no test runner in `frontend/` today; `docs-site` uses vitest, so the pattern exists |
| no hardcoded French left in a translated file | pytest text guard | the established pattern — `test_docs_content.py` and `test_chat_caution_stream.py` already read `.tsx` as text |

Adding vitest is a devDependency, a config file, a script, and a CI step. It is
proposed rather than avoided because the alternative is shipping a new function
with nothing watching it, which is the failure this project has spent the day
correcting.

## Out of scope

- The language the assistant answers in. That would edit `SYSTEM_PROMPT`, which
  this repo treats as code: every gate would have to be re-measured, and a
  number quoted from a French table and restated in Vietnamese raises a real
  question about whether verification still means anything. It can be layered on
  later without redoing any of this.
- Operator screens.
- Server-side per-user preference. There is no user-preferences table, and the
  cookie already survives everything except changing machine.
- Translating `kb.config.locale`'s meaning. It stays the number locale it is.
