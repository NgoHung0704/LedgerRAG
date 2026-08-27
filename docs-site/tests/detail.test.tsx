import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { sourceUrl } from "../src/forge";
import { ComponentDetail } from "../src/views/ComponentDetail";
import { content, type ComponentDetail as Detail } from "../src/content";

describe("layer 3", () => {
  it("links to the exact lines, on whichever forge the build points at", () => {
    // The forge is a build variable, so this pins the SHAPE of the link and
    // the line fragment, not one host.
    expect(sourceUrl("tablerag/api/main.py", 34, 71))
      .toMatch(/^https?:\/\/.+\/tablerag\/api\/main\.py#L34-L71$/);
    expect(sourceUrl("tablerag/api/main.py", 34, 34))
      .toMatch(/^https?:\/\/.+\/tablerag\/api\/main\.py#L34$/);
    // a single line takes no range
    expect(sourceUrl("a.py", 5, 5).endsWith("#L5")).toBe(true);
  });

  it("shows every function the content declares, with its file and line", () => {
    const id = content.components.components[0].id;
    render(<ComponentDetail id={id} lang="vi" />);
    const detail = content.componentDetails[id];
    detail.functions.forEach((fn) => {
      expect(screen.getByText(fn.decl)).toBeTruthy();
      expect(screen.getByText(`${fn.file}:${fn.line}`)).toBeTruthy();
    });
  });

  it("renders the debts, not only the good parts", () => {
    const withDebt = Object.values(content.componentDetails)
      .find((d: Detail) => (d.debts ?? []).length > 0)!;
    render(<ComponentDetail id={withDebt.id} lang="vi" />);
    withDebt.debts.forEach((debt) => {
      expect(screen.getByText(debt.text.vi)).toBeTruthy();
    });
  });

  it("the flow's text version carries the gate labels, not only the boxes", () => {
    const withFlow = Object.values(content.componentDetails)
      .find((d: Detail) => (d.flow?.gates ?? []).length > 0)!;
    render(<ComponentDetail id={withFlow.id} lang="vi" />);
    const text = screen.getAllByTestId("diagram-text")[0].textContent ?? "";
    withFlow.flow!.gates.forEach((gate) => {
      expect(text).toContain(gate.label.vi);
    });
    withFlow.flow!.edges.forEach((edge) => {
      if (edge.label) expect(text).toContain(edge.label.vi);
    });
  });
});
