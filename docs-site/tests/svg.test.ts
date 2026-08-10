import { describe, expect, it } from "vitest";
import { wrapLabel, boxHeight, nodeHeight, laneOffsets, columnGap } from "../src/svg/layout";
import { content } from "../src/content";
import { pick } from "../src/i18n";

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

  it("sizes every node for whichever language is longer", () => {
    // counted from the content, never hardcoded
    content.nodes.nodes.forEach((node) => {
      const vi = boxHeight(wrapLabel(pick(node.label, "vi"), 18));
      const en = boxHeight(wrapLabel(pick(node.label, "en"), 18));
      expect(nodeHeight(node)).toBe(Math.max(vi, en));
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
