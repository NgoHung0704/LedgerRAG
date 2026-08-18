// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, fireEvent } from "@testing-library/react";

Element.prototype.scrollIntoView = () => {};

import ChatPanel from "@/components/ChatPanel";
import { LocaleProvider } from "@/components/LocaleProvider";

const CITATION = {
  index: 1, kind: "table", doc_id: "d1",
  filename: "EPSENS TRANSITION CLIMAT - 810571.pdf",
  page: 2, element_id: "e1", snippet: "…", score: 0.9,
  crop_image_path: null, confidence: 1, needs_review: false,
  from_figure: false, expanded: false,
};

// the shape from the screenshot: the verifier ran, and one figure in the answer
// matched no source — which is what makes useFigureRules walk the answer and
// rewrite its text nodes
const VERIFICATION = {
  enabled: true,
  status: "warnings",
  numbers: [{ raw: "2,63", value: 2.63, status: "verified" },
            { raw: "810571", value: 810571, status: "unverified" }],
  unverified: ["810571"],
};

describe("clicking a source in the answer", () => {
  it("opens it instead of crashing the page", () => {
    const { container } = render(
      <LocaleProvider locale="fr">
        <ChatPanel
          assistantId="a1"
          allKbs={[]}
          conversationId="c1"
          initialMessages={[
            { id: "m1", role: "user", content: "et le graphique ?", citations: [], verification: null },
            {
              id: "m2", role: "assistant",
              content:
                "La volatilité est de 2,63 % [1]. Ces données viennent du "
                + "graphique (EPSENS TRANSITION CLIMAT - 810571.pdf).",
              citations: [CITATION],
              verification: VERIFICATION,
            },
          ] as never}
        />
      </LocaleProvider>,
    );
    const chip = container.querySelector<HTMLButtonElement>(
      "button[title*='810571']",
    );
    expect(chip).not.toBeNull();
    // the figure marking must survive the fix: this crash was caused by the
    // feature, and removing it would also make the test pass
    const marked = container.querySelector('.fig-unverified');
    expect(marked?.textContent).toBe('810571');
    const all = Array.from(container.querySelectorAll('.fig')).map((n) => n.textContent);
    expect(all).toEqual(['2,63 %', '810571']);

    fireEvent.click(chip!);
    expect(container.textContent).toContain('La volatilité');
  });
});
