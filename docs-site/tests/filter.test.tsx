import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComponentGrid } from "../src/views/ComponentGrid";
import { matchesPhase } from "../src/views/PhaseFilter";
import { content } from "../src/content";

describe("phase filter", () => {
  it("dims through a parent, so nothing on the card fights the opacity", () => {
    const phase = content.phases.phases[0].id;
    const { container } = render(<ComponentGrid lang="vi" phase={phase} />);
    const dimmed = container.querySelectorAll("[data-dim-wrapper].dimmed");
    expect(dimmed.length).toBeGreaterThan(0);
    dimmed.forEach((wrapper) => {
      // the class is on the WRAPPER, never on the card itself
      expect(wrapper.querySelector(".dimmed")).toBeNull();
      expect(Number(getComputedStyle(wrapper).opacity)).toBeLessThan(1);
    });
  });

  it("counts from the content, so adding a component is not a failure", () => {
    const phase = content.phases.phases[0].id;
    const expected = content.components.components
      .filter((c) => matchesPhase(c, phase)).length;
    render(<ComponentGrid lang="vi" phase={phase} />);
    expect(screen.getAllByRole("listitem", { current: true }).length)
      .toBe(expected);
  });

  it("lights a component the phase only runs through", () => {
    const traversed = content.components.components.find((c) =>
      c.phases.some((p) => p.relation === "traverses"));
    expect(traversed).toBeDefined();
    const phase = traversed!.phases.find((p) => p.relation === "traverses")!.id;
    expect(matchesPhase(traversed!, phase)).toBe(true);
  });

  it("counts ownership from creates and modifies only", () => {
    content.phases.phases.forEach((phase) => {
      const owners = content.components.components.filter((c) =>
        c.phases.some((p) => p.id === phase.id &&
          (p.relation === "creates" || p.relation === "modifies")));
      expect(owners.length).toBeGreaterThan(0);
    });
  });
});
