"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { MoreVertical, Settings2, Trash2 } from "lucide-react";
import { deleteKb, type KB } from "@/lib/api";
import { Spinner } from "@/components/ui";

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
        className="flex h-7 w-7 items-center justify-center rounded border border-transparent text-slate-400 hover:border-slate-200 hover:bg-white hover:text-slate-700 dark:hover:border-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
      >
        <MoreVertical size={16} />
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-1 w-60 rounded-lg border border-slate-200 bg-white p-1.5 shadow-md dark:border-slate-700 dark:bg-[#1b222a]">
          {!confirming ? (
            <>
              <button
                type="button"
                onClick={() => router.push(`/kb/${kb.id}?settings=1`)}
                className="flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-left text-[13px] text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                <Settings2 size={15} className="text-slate-400" />
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
              <div className="text-[12px] leading-snug text-slate-600">
                Delete <span className="font-semibold">{kb.name}</span> and all
                its documents, vectors and chat history? This can&apos;t be
                undone.
              </div>
              <div className="mt-2.5 flex justify-end gap-1.5">
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  disabled={deleting}
                  className="rounded px-2.5 py-1.5 text-[12px] font-medium text-slate-500 hover:bg-slate-100"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={remove}
                  disabled={deleting}
                  className="inline-flex items-center gap-1.5 rounded bg-red-600 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-red-700 disabled:bg-red-300"
                >
                  {deleting ? <Spinner size={12} /> : <Trash2 size={12} />} Delete
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
