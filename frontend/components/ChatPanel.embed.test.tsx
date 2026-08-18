// @vitest-environment jsdom
/**
 * Embedded, ChatPanel talks to the embed endpoint and to nothing else.
 *
 * The token is the credential; posting to /api/assistants/... from an embedded
 * page would 401 the moment authentication is switched on, which is the one
 * thing the token exists to survive.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, fireEvent } from "@testing-library/react";

Element.prototype.scrollIntoView = () => {};

import ChatPanel from "@/components/ChatPanel";
import { LocaleProvider } from "@/components/LocaleProvider";

const calls: string[] = [];

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(String(url));
      return { ok: true, status: 200, body: null, json: async () => ({}) };
    }) as never,
  );
});

describe("an embedded ChatPanel", () => {
  it("asks the embed endpoint, carrying the token", async () => {
    const { container } = render(
      <LocaleProvider locale="fr">
        <ChatPanel embedToken="tok_abc" allKbs={[]} />
      </LocaleProvider>,
    );
    const box = container.querySelector("textarea")!;
    fireEvent.change(box, { target: { value: "quelle volatilité ?" } });
    fireEvent.submit(box.closest("form")!);
    await vi.waitFor(() =>
      expect(calls.some((u) => u.includes("/api/embed/tok_abc/chat"))).toBe(true),
    );
    expect(calls.some((u) => u.includes("/api/assistants/"))).toBe(false);
  });

  it("offers no scope picker: its context is fixed by the token", () => {
    const { container } = render(
      <LocaleProvider locale="fr">
        <ChatPanel
          embedToken="tok_abc"
          allKbs={[
            { id: "a", name: "ACCORDS", description: "", config: {}, created_at: "" },
            { id: "b", name: "GLOSSAIRE", description: "", config: {}, created_at: "" },
          ] as never}
        />
      </LocaleProvider>,
    );
    expect(container.textContent).not.toContain("Chercher dans");
  });
});
