"use client";

import { useT } from "@/components/LocaleProvider";
import { useEffect, useRef, useState } from "react";
import { MessagesSquare, MoreVertical, Settings2 } from "lucide-react";
import type { Assistant } from "@/lib/api";

/** Per-card actions on the Assistants list. Sits over the card as a sibling of
 *  the card's Link — not nested inside it — so its button is valid HTML and its
 *  clicks never trigger the card navigation.
 *
 *  Settings opens the same form the assistant's own page uses, right here, so
 *  changing which knowledge bases it can search doesn't cost a round trip into
 *  the assistant and back out. */
export default function AssistantCardMenu({
  assistant,
  onSettings,
  onOpen,
}: {
  assistant: Assistant;
  onSettings: () => void;
  onOpen: () => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const choose = (fn: () => void) => () => {
    setOpen(false);
    fn();
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        aria-label={`Actions for ${assistant.name}`}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((o) => !o)}
        className="flex h-7 w-7 items-center justify-center rounded border border-transparent text-ink-subtle transition-colors hover:border-line hover:bg-surface hover:text-ink"
      >
        <MoreVertical size={16} aria-hidden="true" />
      </button>

      {open && (
        <div
          role="menu"
          className="pop max-h-[min(30rem,70vh)] overflow-y-auto absolute right-0 z-20 mt-1 w-56 origin-top-right rounded-lg border border-line bg-surface p-1.5 shadow-lift"
        >
          <button
            type="button"
            role="menuitem"
            onClick={choose(onSettings)}
            className="flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-left text-[13px] text-ink transition-colors hover:bg-surface-sunken"
          >
            <Settings2 size={15} className="text-ink-subtle" aria-hidden="true" />
            {t("asst.settings")}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={choose(onOpen)}
            className="flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-left text-[13px] text-ink transition-colors hover:bg-surface-sunken"
          >
            <MessagesSquare size={15} className="text-ink-subtle" aria-hidden="true" />
            {t("asst.open_conversations")}
          </button>
        </div>
      )}
    </div>
  );
}
