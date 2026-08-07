"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { MoreVertical, Settings2, Trash2 } from "lucide-react";
import { deleteKb, type KB } from "@/lib/api";
import { Button } from "@/components/ui";

// Per-card actions on the Knowledge Bases list: open settings, or delete.
// Sits over the card (a sibling of the card's Link, not nested in it) so its
// button is valid HTML and its clicks never trigger the card navigation.
export default function KbCardMenu({
  kb,
  onChanged,
}: {
  kb: KB;
  onChanged: () => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setConfirming(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const remove = async () => {
    setDeleting(true);
    try {
      await deleteKb(kb.id);
      onChanged();
    } catch {
      setDeleting(false);
      setConfirming(false);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        aria-label="Knowledge base actions"
        onClick={() => setOpen((o) => !o)}
        className="flex h-7 w-7 items-center justify-center rounded border border-transparent text-ink-subtle hover:border-line hover:bg-surface hover:text-ink"
      >
        <MoreVertical size={16} />
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-1 w-60 rounded-lg border border-line bg-surface p-1.5 shadow-md">
          {!confirming ? (
            <>
              <button
                type="button"
                onClick={() => router.push(`/kb/${kb.id}?settings=1`)}
                className="flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-left text-[13px] text-ink hover:bg-surface-sunken"
              >
                <Settings2 size={15} className="text-ink-subtle" />
                Settings &amp; rename
              </button>
              <button
                type="button"
                onClick={() => setConfirming(true)}
                className="flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-left text-[13px] text-red-600 hover:bg-red-50"
              >
                <Trash2 size={15} /> Delete knowledge base
              </button>
            </>
          ) : (
            <div className="p-1.5">
              <div className="text-[12px] leading-snug text-ink-muted">
                Delete <span className="font-semibold">{kb.name}</span> and all
                its documents, vectors and chat history? This can&apos;t be
                undone.
              </div>
              <div className="mt-2.5 flex justify-end gap-1.5">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setConfirming(false)}
                  disabled={deleting}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="destructive"
                  onClick={remove}
                  loading={deleting}
                  icon={<Trash2 size={12} />}
                >
                  Delete
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
