import { describe, expect, it } from "vitest";

import { citationWeights } from "./citationWeight";

describe("citationWeights", () => {
  it("marks the best sources strong and the trailing ones weak", () => {
    expect(citationWeights([0.92, 0.88, 0.55, 0.12, 0.09])).toEqual([
      "strong",
      "strong",
      "normal",
      "weak",
      "weak",
    ]);
  });

  it("says nothing when the sources are genuinely equal", () => {
    // the honest case, and the reason this is not a plain ratio to the best:
    // eight sources the reranker scored alike carry no hierarchy, and drawing
    // one would tell the reader something the data does not say
    expect(citationWeights([0.81, 0.8, 0.8, 0.79])).toEqual([
      "normal",
      "normal",
      "normal",
      "normal",
    ]);
  });

  it("works on any scale, because it reads the spread and not the value", () => {
    // with the reranker disabled these are RRF fusion scores, two orders of
    // magnitude smaller. The same shape must give the same answer.
    expect(citationWeights([0.031, 0.03, 0.018, 0.004])).toEqual(
      citationWeights([0.031, 0.03, 0.018, 0.004].map((s) => s * 1000)),
    );
  });

  it("pulls out the single outlier when everything else is close", () => {
    const w = citationWeights([0.9, 0.89, 0.88, 0.87, 0.1]);
    expect(w[4]).toBe("weak");
    expect(w.slice(0, 4)).toEqual(["strong", "strong", "strong", "strong"]);
  });

  it("emphasises nothing for a single source", () => {
    expect(citationWeights([0.42])).toEqual(["normal"]);
  });

  it("emphasises nothing when no source has a score at all", () => {
    // expanded neighbours arrive with 0.0 on purpose — they were never
    // retrieved, and a borrowed score would let them compete
    expect(citationWeights([0, 0, 0])).toEqual(["normal", "normal", "normal"]);
  });
});
