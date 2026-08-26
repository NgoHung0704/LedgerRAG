import { describe, expect, it } from "vitest";
import { wrapLabel, boxHeight, nodeHeight, laneOffsets, columnGap } from "../src/svg/layout";
import { content } from "../src/content";
import { LANGS, pick } from "../src/i18n";

describe("svg text", () => {
  it("wraps a long label instead of letting it run out of its box", () => {
    const lines = wrapLabel("Reverse proxy and single sign-on, header trusted", 18);
    expect(lines.length).toBeGreaterThan(1);
    lines.forEach((line) => expect(line.length).toBeLessThanOrEqual(18));
  });

  it("grows the box with the number of lines", () => {
    expect(boxHeight(wrapLabel("short", 18))).toBeLessThan(
      boxHeight(wrapLabel("Reverse proxy and single sign-on, header trusted", 18)));
  });

  it("sizes every node for the LONGEST language, not just two of them", () => {
    // Counted from the content and from LANGS, never hardcoded: adding a
    // language must widen this assertion by itself. French made some labels
    // wrap onto a third line, which is exactly what this catches.
    content.nodes.nodes.forEach((node) => {
      const each = LANGS.map((lang) =>
        boxHeight(wrapLabel(pick(node.label, lang), 18)));
      expect(nodeHeight(node)).toBe(Math.max(...each));
    });
  });
});

describe("edge lanes", () => {
  it("gives parallel edges distinct lanes", () => {
    const offsets = laneOffsets(5);
    expect(new Set(offsets).size).toBe(5);
  });

  it("widens the gap so five lines are not crushed into forty pixels", () => {
    expect(columnGap(5)).toBeGreaterThan(columnGap(1));
    expect(columnGap(5)).toBeGreaterThanOrEqual(5 * 24);
  });
});
