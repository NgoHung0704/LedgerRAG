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
