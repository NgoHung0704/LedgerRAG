// @vitest-environment jsdom
/**
 * A dialog must not steal focus back from the field you are typing in.
 *
 * `useDialog` listed `onClose` in its effect dependencies, and every caller
 * passes an inline arrow — `onClose={() => setShowCreate(false)}` — which is a
 * new function on every parent render. The knowledge-base list polls every
 * three seconds while a document is ingesting, so the parent re-rendered on a
 * timer, the effect tore down and re-ran, and its cleanup did this:
 *
 *     if (opener?.isConnected) opener.focus?.();
 *
 * Focus jumped back to the button that had opened the dialog, then to the first
 * field. Reported as: "you type for a while and suddenly you are out."
 *
 * Two traps in testing it, both of which produced green tests that proved
 * nothing before this file was written properly:
 *
 * 1. A re-render alone does not reproduce it. The NEW `onClose` identity is
 *    what re-runs the effect, so a harness that memoises the callback passes
 *    whether the bug is there or not.
 * 2. jsdom performs no layout, so `offsetParent` is always null and
 *    `focusables()` — which filters on it — returns nothing. The focus moves
 *    then land on unfocusable elements and quietly do nothing, so the stolen
 *    focus never shows. The shim below is what makes this file test the real
 *    code path rather than an empty one.
 */
import { useState } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { Modal } from "./ui";

beforeAll(() => {
  // see trap 2 above: without this, useDialog sees zero focusable elements
  Object.defineProperty(HTMLElement.prototype, "offsetParent", {
    configurable: true,
    get(this: HTMLElement) {
      return this.parentElement;
    },
  });
});

// vitest runs without `globals`, so testing-library never registers its own
// afterEach — and Modal portals into document.body, which would otherwise pile
// up across tests
afterEach(cleanup);

/** Open button, then a dialog handed a FRESH onClose on every parent render —
 *  exactly what all eight callers in this app do. */
function Harness() {
  const [open, setOpen] = useState(false);
  const [, bump] = useState(0);
  return (
    <div>
      <button onClick={() => setOpen(true)}>ouvrir</button>
      <button onClick={() => bump((n) => n + 1)}>rerender</button>
      {open && (
        <Modal title="Nouvelle base" onClose={() => setOpen(false)}>
          <input aria-label="nom" />
          <input aria-label="description" />
        </Modal>
      )}
    </div>
  );
}

function openDialog() {
  render(<Harness />);
  const opener = screen.getByText("ouvrir");
  opener.focus();
  fireEvent.click(opener);
  return opener;
}

describe("a dialog under a re-rendering parent", () => {
  it("leaves focus where the typist put it", () => {
    openDialog();
    const description = screen.getByLabelText("description");
    description.focus();

    // the parent re-renders: a poll tick, a status refresh, anything
    fireEvent.click(screen.getByText("rerender"));

    expect(document.activeElement).toBe(description);
  });

  it("survives a parent that re-renders repeatedly", () => {
    // three seconds of typing is several ticks, not one
    openDialog();
    const nom = screen.getByLabelText("nom");
    nom.focus();
    for (let i = 0; i < 5; i++) {
      fireEvent.click(screen.getByText("rerender"));
    }
    expect(document.activeElement).toBe(nom);
  });

  it("never hands focus back to the opener while the dialog is still open", () => {
    // the cleanup path directly: restoring focus to the opener is correct on
    // CLOSE and wrong on every re-render
    const opener = openDialog();
    const spy = vi.spyOn(opener, "focus");
    screen.getByLabelText("nom").focus();

    fireEvent.click(screen.getByText("rerender"));

    expect(spy).not.toHaveBeenCalled();
  });

  it("still focuses a field when the dialog opens", () => {
    // the fix must not cost the initial focus: a dialog that opens with focus
    // on the page behind it is a keyboard trap of its own
    openDialog();
    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("hands focus back to the opener when the dialog really closes", () => {
    // the behaviour the cleanup exists for, which must survive the fix
    const opener = openDialog();
    fireEvent.click(screen.getByLabelText("Close"));
    expect(document.activeElement).toBe(opener);
  });
});
