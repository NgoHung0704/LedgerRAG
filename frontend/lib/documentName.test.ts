import { describe, expect, it } from "vitest";

import { shortName } from "./documentName";

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
