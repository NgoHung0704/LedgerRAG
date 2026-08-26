import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SystemMap } from "../src/views/SystemMap";
import { content } from "../src/content";
import { pick } from "../src/i18n";

/** Every ordered pair of nodes an edge connects — one wire is drawn per pair,
 *  counted from the content so adding a contract family is not a failure. */
const pairs = () => [...new Set(
  content.edges.edges.map((edge) => `${edge.from}~${edge.to}`))];

describe("the board", () => {
  it("draws one wire per pair of modules, not one per contract family", () => {
    const { container } = render(<SystemMap lang="vi" phase={null} />);
    expect(container.querySelectorAll("[data-wire]").length).toBe(pairs().length);
    expect(pairs().length).toBeLessThan(content.edges.edges.length);
  });

  it("gives every wire a path of its own", () => {
    const { container } = render(<SystemMap lang="vi" phase={null} />);
    const shapes = pairs().map((id) => container
      .querySelector<SVGPathElement>(`path[data-wire-path="${id}"]`)!
      .getAttribute("d")!);
    expect(new Set(shapes).size).toBe(shapes.length);
  });

  it("counts the families riding a shared wire", () => {
    const { container } = render(<SystemMap lang="vi" phase={null} />);
    const shared = pairs().filter((id) => content.edges.edges
      .filter((e) => `${e.from}~${e.to}` === id).length > 1);
    expect(shared.length).toBeGreaterThan(0);
    shared.forEach((id) => {
      const expected = content.edges.edges
        .filter((e) => `${e.from}~${e.to}` === id).length;
      const chip = container.querySelector(`[data-wire="${id}"] .chip text`)!;
      expect(chip.textContent).toBe(String(expected));
    });
  });

  it("every wire is reachable by keyboard and announced", () => {
    const { container } = render(<SystemMap lang="vi" phase={null} />);
    container.querySelectorAll("[data-wire]").forEach((wire) => {
      expect(wire.getAttribute("tabindex")).toBe("0");
      expect(wire.getAttribute("aria-label")).toBeTruthy();
      expect(wire.closest("[aria-hidden='true']")).toBeNull();
    });
  });

  it("dims through wrappers when a wire is selected, sparing its two ends", () => {
    const wire = content.edges.edges[0];
    const id = `${wire.from}~${wire.to}`;
    const { container } = render(
      <SystemMap
        lang="vi" phase={null}
        route={{ lang: "vi", view: "map", id: null, phase: null,
                 sub: { kind: "edge", id } }}
      />);
    const board = container.querySelector(".board")!;
    expect(board.classList.contains("board-spotlight")).toBe(true);
    [wire.from, wire.to].forEach((node) => {
      const wrapper = container.querySelector(`[data-node="${node}"]`)!;
      expect(wrapper.classList.contains("dimmed")).toBe(false);
    });
    const others = content.nodes.nodes
      .filter((n) => n.id !== wire.from && n.id !== wire.to);
    others.forEach((node) => {
      const wrapper = container.querySelector(`[data-node="${node.id}"]`)!;
      expect(wrapper.classList.contains("dimmed")).toBe(true);
      // the class is on the WRAPPER, never on the shape inside it
      expect(wrapper.querySelector(".dimmed")).toBeNull();
      expect(Number(getComputedStyle(wrapper).opacity)).toBeLessThan(1);
    });
  });

  it("the text version still carries EVERY contract family, not just the wires", () => {
    render(<SystemMap lang="vi" phase={null} />);
    const text = screen.getByTestId("diagram-text").textContent ?? "";
    content.edges.edges.forEach((edge) => {
      expect(text).toContain(pick(edge.label, "vi"));
    });
    content.nodes.nodes.forEach((node) => {
      expect(text).toContain(pick(node.label, "vi"));
    });
  });

  it("leaves no trace of the other languages after a switch", () => {
    const { container, rerender } = render(<SystemMap lang="vi" phase={null} />);
    rerender(<SystemMap lang="fr" phase={null} />);
    const text = container.textContent ?? "";
    content.nodes.nodes.forEach((node) => {
      expect(text).toContain(pick(node.label, "fr"));
      // A name that reads the same in two languages is not a leftover.
      if (node.label.vi !== node.label.fr) {
        expect(text).not.toContain(pick(node.label, "vi"));
      }
    });
  });
});
