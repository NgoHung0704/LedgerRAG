import { describe, expect, it } from "vitest";

import { inlineLabel, shortName } from "./documentName";

describe("shortName", () => {
  it("drops the extension", () => {
    expect(shortName("Glossaire-Classification.pdf")).toBe(
      "Glossaire-Classification",
    );
  });

  it("keeps the reference number, which is what tells editions apart", () => {
    expect(shortName("EPSENS FLEXI TAUX COURT ISR SOLIDAIRE - 100312.pdf")).toBe(
      "EPSENS FLEXI TAUX COURT ISR SOLIDAIRE - 100312",
    );
  });

  it("only drops the LAST dot group, not a version inside the name", () => {
    expect(shortName("notice.v2.docx")).toBe("notice.v2");
  });

  it("leaves a name with no extension alone", () => {
    expect(shortName("Avenant du 11 juillet 2023")).toBe(
      "Avenant du 11 juillet 2023",
    );
  });

  it("does not mistake a trailing date for an extension", () => {
    // "2023" is four characters after a dot, which is exactly the shape of an
    // extension — the guard is that extensions are letters or digits and this
    // is caught by nothing else, so it is pinned
    expect(shortName("Cotation emplois CETIAT 2023_07_27.pdf")).toBe(
      "Cotation emplois CETIAT 2023_07_27",
    );
  });
});

describe("inlineLabel", () => {
  it("names the document and the page, inside the sentence", () => {
    expect(inlineLabel("Glossaire.pdf", 4)).toBe("Glossaire · p.4");
  });

  it("clips a long name so one citation cannot swallow a line", () => {
    const label = inlineLabel(
      "EPSENS FLEXI TAUX COURT ISR SOLIDAIRE - 100312.pdf",
      2,
    );
    expect(label.endsWith("· p.2")).toBe(true);
    expect(label.length).toBeLessThanOrEqual(30);
    expect(label).toContain("…");
  });

  it("clips from the END, keeping the words a reader scans for", () => {
    // "EPSENS FLEXI" identifies the fund; the reference number does not, and a
    // middle-ellipsis would keep the digits and drop the name
    expect(inlineLabel("EPSENS FLEXI TAUX COURT ISR SOLIDAIRE - 100312.pdf", 2))
      .toMatch(/^EPSENS FLEXI/);
  });

  it("does not clip a name that already fits", () => {
    expect(inlineLabel("Avenant 2023.pdf", 11)).toBe("Avenant 2023 · p.11");
  });
});
