import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SystemMap } from "../src/views/SystemMap";
import { content } from "../src/content";
import { pick } from "../src/i18n";

describe("system map", () => {
  it("puts two edges between the same pair on different paths", () => {
    const { container } = render(<SystemMap lang="vi" phase={null} />);
    const pairs = new Map<string, string[]>();
    content.edges.edges.forEach((edge) => {
      const key = [edge.from, edge.to].sort().join("~");
      const d = container.querySelector<SVGPathElement>(
        `path[data-edge="${edge.id}"]`)!.getAttribute("d")!;
      pairs.set(key, [...(pairs.get(key) ?? []), d]);
    });
    pairs.forEach((ds) => expect(new Set(ds).size).toBe(ds.length));
  });

  it("puts each edge label at the middle of its own turn, not the source box", () => {
    const { container } = render(<SystemMap lang="vi" phase={null} />);
    const points = content.edges.edges.map((edge) => {
      const label = container.querySelector(`text[data-edge-label="${edge.id}"]`)!;
      return `${label.getAttribute("x")},${label.getAttribute("y")}`;
    });
    expect(new Set(points).size).toBe(points.length);
  });

  it("every clickable shape is reachable and announced", () => {
    render(<SystemMap lang="vi" phase={null} />);
    content.edges.edges.forEach((edge) => {
      const el = screen.getByLabelText(pick(edge.label, "vi"));
      expect(el.getAttribute("tabindex")).toBe("0");
      expect(el.closest("[aria-hidden='true']")).toBeNull();
    });
  });

  it("the text version carries the edge labels AND the node labels", () => {
    render(<SystemMap lang="vi" phase={null} />);
    const text = screen.getByTestId("diagram-text").textContent ?? "";
    content.edges.edges.forEach((edge) => {
      expect(text).toContain(pick(edge.label, "vi"));
    });
    content.nodes.nodes.forEach((node) => {
      expect(text).toContain(pick(node.label, "vi"));
    });
  });

  it("leaves no trace of the other language after a switch", () => {
    const { container, rerender } = render(<SystemMap lang="vi" phase={null} />);
    rerender(<SystemMap lang="en" phase={null} />);
    const text = container.textContent ?? "";
    content.nodes.nodes.forEach((node) => {
      expect(text).toContain(pick(node.label, "en"));
      // A label that reads the same in both languages — "Reverse proxy / SSO"
      // — is not a leftover, so it is the only thing exempted here.
      if (node.label.vi !== node.label.en) {
        expect(text).not.toContain(pick(node.label, "vi"));
      }
    });
  });
});
