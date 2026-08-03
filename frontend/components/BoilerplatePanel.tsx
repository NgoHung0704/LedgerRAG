"use client";

import { useEffect, useState } from "react";
import { Eraser } from "lucide-react";
import {
  excludeBoilerplate,
  scanBoilerplate,
  type BoilerplateCandidate,
} from "@/lib/api";
import { Button, Modal, Spinner } from "@/components/ui";

/** Reviewable boilerplate removal: scan finds running headers/footers/page
 * numbers (repetition across pages at a margin); the user confirms which to
 * exclude from retrieval. Nothing is auto-deleted — excluded elements keep
 * their image and stay visible in the inspector, just out of retrieval. */
export default function BoilerplatePanel({
  docId,
  onClose,
  onExcluded,
}: {
  docId: string;
  onClose: () => void;
  onExcluded: () => void;
}) {
  const [cands, setCands] = useState<BoilerplateCandidate[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    scanBoilerplate(docId)
      .then((c) => {
        setCands(c);
        setSelected(new Set(c.map((x) => x.element_id))); // default: all checked
      })
      .catch((e) => setError(String(e)));
  }, [docId]);

  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const exclude = async () => {
    if (selected.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      await excludeBoilerplate(docId, Array.from(selected));
      onExcluded();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Detect boilerplate — running headers, footers & page numbers"
      onClose={onClose}
      wide
    >
      {cands === null ? (
        <div className="flex justify-center py-10">
          <Spinner size={20} />
        </div>
      ) : error ? (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      ) : cands.length === 0 ? (
        <p className="py-6 text-center text-sm text-ink-muted">
          No running headers, footers or page numbers detected — nothing repeats
          across pages at a margin.
        </p>
      ) : (
        <div className="space-y-3">
          <p className="rounded-lg bg-surface-sunken px-3 py-2 text-xs leading-5 text-ink-muted dark:bg-slate-800/60">
            These text blocks repeat across pages at the top/bottom, or look like
            page numbers. Excluding them removes them from retrieval so they
            don&apos;t pollute answers — the elements and their images stay in the
            inspector. Tables are never touched. Uncheck anything you want to
            keep.
          </p>

          <div className="max-h-[50vh] divide-y divide-slate-100 overflow-auto rounded-lg border border-line dark:divide-slate-800">
            {cands.map((c) => (
              <label
                key={c.element_id}
                className="flex cursor-pointer items-start gap-2.5 px-3 py-2 hover:bg-surface-sunken dark:hover:bg-slate-800/50"
              >
                <input
                  type="checkbox"
                  checked={selected.has(c.element_id)}
                  onChange={() => toggle(c.element_id)}
                  className="mt-0.5 h-4 w-4 rounded border-line-strong text-indigo-600"
                />
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-ink">
                    {c.text || <span className="italic text-ink-subtle">(empty)</span>}
                  </div>
                  <div className="text-[11px] text-ink-subtle">
                    page {c.page} · {c.reason}
                  </div>
                </div>
              </label>
            ))}
          </div>

          {error && <p className="text-xs text-red-600">{error}</p>}

          <div className="flex items-center gap-3 border-t border-line pt-3">
            <span className="text-xs text-ink-subtle">
              {selected.size} of {cands.length} selected
            </span>
            <div className="ml-auto flex gap-2">
              <Button variant="secondary" onClick={onClose} disabled={busy}>
                Cancel
              </Button>
              <Button onClick={exclude} disabled={busy || selected.size === 0}>
                {busy ? (
                  <Spinner size={14} />
                ) : (
                  <Eraser size={14} />
                )}
                Exclude {selected.size} from retrieval
              </Button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
