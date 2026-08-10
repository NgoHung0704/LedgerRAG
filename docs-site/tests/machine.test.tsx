import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MachineDiagram } from "../src/views/MachineDiagram";
import { content } from "../src/content";

describe("assembly line", () => {
  it("lights the parts of the filtered phase and dims the rest, via wrappers", () => {
    const machine = content.machines.machines[0];
    const phase = machine.parts.flatMap((p) => p.phases)[0];
    const { container } = render(
      <MachineDiagram id={machine.id} lang="vi" phase={phase} />);
    machine.parts.forEach((part) => {
      const wrapper = container.querySelector(`[data-part="${part.id}"]`)!;
      const lit = part.phases.includes(phase);
      expect(wrapper.classList.contains("dimmed")).toBe(!lit);
      expect(wrapper.querySelector(".dimmed")).toBeNull();
    });
  });

  it("names every exit and every edge label in the text version", () => {
    const machine = content.machines.machines[0];
    render(<MachineDiagram id={machine.id} lang="vi" phase={null} />);
    const text = screen.getByTestId("diagram-text").textContent ?? "";
    machine.exits.forEach((exit) => expect(text).toContain(exit.label.vi));
    machine.edges.forEach((edge) => {
      if ("label" in edge && edge.label) expect(text).toContain(edge.label.vi);
    });
  });
});
