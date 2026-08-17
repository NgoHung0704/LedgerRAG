/** The number formats a knowledge base can declare, each named in its own
 *  language and shown with the shape it produces.
 *
 *  Data, not interface copy, and that is why it lives outside the message
 *  catalogues: someone looking for the French convention scans for "Français",
 *  not for whatever the current interface language happens to call French —
 *  the same reason the language picker's own options are never translated.
 *
 *  `value` is what goes into `kb.config.locale`, which `core/numbers.py` reads
 *  to decide whether `1 234,56` is one thousand two hundred and thirty-four
 *  point five six. It has nothing to do with the language of this interface.
 *
 *  "Not specified" is the one entry here that IS interface copy, so it carries
 *  a message key instead of a label. */
import type { MessageKey } from "@/messages/en";

export const NUMBER_LOCALES: {
  value: string;
  label?: string;
  labelKey?: MessageKey;
}[] = [
  { value: "", labelKey: "kb.locale_unspecified" },
  { value: "fr", label: "Français (1 234,56)" },
  { value: "de", label: "Deutsch (1.234,56)" },
  { value: "en", label: "English (1,234.56)" },
  { value: "es", label: "Español (1.234,56)" },
  { value: "it", label: "Italiano (1.234,56)" },
  { value: "pt", label: "Português (1.234,56)" },
];
