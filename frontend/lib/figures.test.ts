import { describe, expect, it } from "vitest";

import { splitFigures } from "./figures";

const figures = (s: string) =>
  splitFigures(s).filter((p) => p.figure).map((p) => p.text);
const rejoin = (s: string) => splitFigures(s).map((p) => p.text).join("");

describe("splitFigures", () => {
  it("finds the figures an answer states", () => {
    // "3" in "3 ans" is not one: a lone digit is a period label, a list marker
    // or a day in a date, never a value the answer is staking a claim on
    expect(figures("La volatilité 3 ans est de 2,63 % contre 2,74 %.")).toEqual([
      "2,63 %", "2,74 %",
    ]);
  });

  it("never loses or adds a character", () => {
    // the parts are rendered in order, so anything dropped here is text the
    // reader silently never sees
    for (const s of [
      "La performance est de -4,31 % sur 1 mois.",
      "1 234,56 € au 31/12/2020",
      "aucun chiffre ici",
      "",
      "12",
    ]) {
      expect(rejoin(s)).toBe(s);
    }
  });

  it("leaves a lone digit as ordinary text", () => {
    // "1." opening a list, or a day in a date
    expect(figures("1. Le premier point")).toEqual([]);
  });

  it("keeps a French thousands separator inside one figure", () => {
    expect(figures("un actif net de 1 234,56 €")).toEqual(["1 234,56 €"]);
  });

  it("returns the whole string untouched when there is nothing to mark", () => {
    expect(splitFigures("rien à signaler")).toEqual([
      { text: "rien à signaler", figure: false },
    ]);
  });
});
