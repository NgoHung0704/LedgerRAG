// @vitest-environment jsdom
/**
 * ChatPanel must mount.
 *
 * It is the one screen the server never renders: /kb/[id] opens on the
 * Documents tab, so clicking Chat is the first time this component runs, and it
 * runs only in the browser. A hook added in the wrong place, an import that
 * resolves at type-check but throws at runtime, a helper deleted while still
 * called — none of that shows in `tsc`, in `next build`, or in the server log.
 */
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

// jsdom implements neither; neither is what is under test
Element.prototype.scrollIntoView = () => {};

import ChatPanel from "@/components/ChatPanel";
import { LocaleProvider } from "@/components/LocaleProvider";
import type { KB } from "@/lib/api";

const KBS = [
  { id: "a", name: "ACCORDS", description: "", config: {}, created_at: "" },
  { id: "b", name: "GLOSSAIRE", description: "", config: {}, created_at: "" },
] as KB[];

function mount(ui: React.ReactNode) {
  return render(<LocaleProvider locale="fr">{ui}</LocaleProvider>);
}

describe("ChatPanel mounts", () => {
  it("inside a knowledge base, with a scope picker", () => {
    const { container } = mount(<ChatPanel kbId="a" allKbs={KBS} />);
    expect(container.querySelector("textarea")).not.toBeNull();
    expect(container.textContent).toContain("Chercher dans");
  });

  it("with a single knowledge base, where no scope picker shows", () => {
    const { container } = mount(<ChatPanel kbId="a" allKbs={[KBS[0]]} />);
    expect(container.querySelector("textarea")).not.toBeNull();
    expect(container.textContent).not.toContain("Chercher dans");
  });

  it("standalone, before the knowledge bases have loaded", () => {
    // /ask renders this with an empty list on the first paint
    const { container } = mount(<ChatPanel allKbs={[]} />);
    expect(container.querySelector("textarea")).not.toBeNull();
  });

  it("as an assistant, replaying a stored conversation with citations", () => {
    // the path that exercises the answer body: markers in the sentence, the
    // source list under it, the weighting of both
    const { container } = mount(
      <ChatPanel
        assistantId="asst-1"
        allKbs={KBS}
        conversationId="conv-1"
        initialMessages={[
          { id: "m1", role: "user", content: "quelle volatilité ?", citations: [], verification: null },
          {
            id: "m2",
            role: "assistant",
            content: "La volatilité 3 ans est de 2,63 % [1].",
            citations: [
              {
                index: 1, kind: "table", doc_id: "d1",
                filename: "EPSENS OBLIGATIONS VERTES ISR - 6006.pdf",
                page: 2, element_id: "e1", snippet: "…", score: 0.9,
                crop_image_path: null, confidence: 1, needs_review: false,
                from_figure: false, expanded: false,
              },
            ],
            verification: null,
          },
        ] as never}
      />,
    );
    expect(container.textContent).toContain("EPSENS OBLIGATIONS");
    expect(container.textContent).toContain("p.2");
  });
});
