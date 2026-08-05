"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Table2,
  X,
} from "lucide-react";
import {
  elementImageUrl,
  getElement,
  pageImageUrl,
  type Citation,
  type ElementDetail,
} from "@/lib/api";
import { IconButton, Portal, Spinner, useDialog } from "@/components/ui";

/** Citation click-through as a right-side drawer: a confidence read-out, the
 * parsed table HTML, and the ORIGINAL crop image (principle #3 — the trace back
 * to the source is always one click away, never hidden). */
export default function SourceModal({
  citation,
  onClose,
}: {
  citation: Citation;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<ElementDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    getElement(citation.element_id)
      .then(setDetail)
      .catch(() => setFailed(true));
  }, [citation.element_id]);

  // slide in on mount
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // animate out, THEN let the parent unmount us
  const close = useCallback(() => {
    setShown(false);
    setTimeout(onClose, 300);
  }, [onClose]);

  // Escape, the scroll lock, the focus trap and handing focus back to the
  // citation that opened the drawer all come from the shared dialog hook
  const ref = useDialog(close);

  const rev = citation.needs_review;
  const conf = detail?.confidence;

  return (
    <Portal>
    <div className="fixed inset-0 z-50">
      <div
        onClick={close}
        className={`absolute inset-0 bg-slate-900/40 transition-opacity duration-300 ${
          shown ? "opacity-100" : "opacity-0"
        }`}
      />
      <aside
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={`Source ${citation.index}`}
        className={`absolute right-0 top-0 flex h-full w-[440px] max-w-[92vw] flex-col border-l border-line bg-surface shadow-xl transition-transform duration-300 ease-out ${
          shown ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* header */}
        <div className="flex items-start gap-3 border-b border-line px-5 py-4">
          <span
            className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
              rev
                ? "bg-amber-50 text-amber-600 dark:bg-amber-950/50 dark:text-amber-300"
                : "bg-indigo-50 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300"
            }`}
          >
            {citation.kind === "table" ? <Table2 size={17} /> : <FileText size={17} />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-subtle">
              Source [{citation.index}]
            </div>
            <div className="truncate font-serif text-[15px] font-semibold text-ink">
              {citation.filename}
            </div>
            <div className="font-mono text-xs text-ink-muted">
              page {citation.page}
              {citation.kind === "table" ? " · table" : ""}
            </div>
          </div>
          <IconButton label="Close source" onClick={close}>
            <X size={18} />
          </IconButton>
        </div>

        {/* body */}
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {conf != null && <ConfidenceBar value={conf} rev={rev} />}

          {citation.from_figure && (
            <div className="flex items-start gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3.5 py-3 text-sm text-indigo-800 dark:border-indigo-900/60 dark:bg-indigo-950/40 dark:text-indigo-200">
              <ImageIcon size={16} className="mt-0.5 shrink-0" />
              <div>
                <div className="font-medium">
                  This source is a description of an image.
                </div>
                <div className="mt-0.5 text-[13px]">
                  The parser model read the figure below and wrote what it
                  shows. That description is not text printed in the document —
                  the image is what the document actually says.
                </div>
              </div>
            </div>
          )}

          {rev && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <div>
                <div className="font-medium">
                  This parse is unreliable, so no figure is asserted from it.
                </div>
                <div className="mt-0.5 text-[13px]">
                  The image below is the record. Read the numbers there — the
                  assistant will not quote them for you.
                </div>
              </div>
            </div>
          )}

          {failed ? (
            <p className="text-sm text-red-700 dark:text-red-400">
              This source could not be loaded. It may have been deleted, or the
              document reprocessed since the answer was written.
            </p>
          ) : detail === null ? (
            <div className="flex justify-center py-10">
              <Spinner size={20} />
            </div>
          ) : (
            <>
              {detail.table?.summary && (
                <p className="text-[13px] italic leading-5 text-ink-muted">
                  {detail.table.summary}
                </p>
              )}

              {detail.table?.html && !rev && (
                <div>
                  <SectionLabel>
                    Parsed table
                    {detail.table.parse_strategy
                      ? ` (${detail.table.parse_strategy})`
                      : ""}
                  </SectionLabel>
                  <div
                    className="doc-table max-h-72 overflow-auto rounded-lg border border-line p-2"
                    dangerouslySetInnerHTML={{ __html: detail.table.html }}
                  />
                </div>
              )}

              {detail.type === "text" && citation.snippet && (
                <blockquote className="border-l-2 border-line pl-3 text-sm leading-6 text-ink-muted">
                  {citation.snippet}
                  {citation.snippet.length >= 240 && "…"}
                </blockquote>
              )}

              <div>
                <SectionLabel>As printed in the document</SectionLabel>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={elementImageUrl(detail.id)}
                  alt={`The original crop from ${citation.filename}, page ${citation.page}`}
                  className="w-full rounded-lg border border-line bg-surface object-contain"
                />
              </div>
            </>
          )}
        </div>

        {/* footer */}
        <div className="border-t border-line px-5 py-3.5">
          <a
            href={pageImageUrl(citation.doc_id, citation.page)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-300"
          >
            <ExternalLink size={13} aria-hidden="true" /> Open page{" "}
            {citation.page} in full
          </a>
        </div>
      </aside>
    </div>
    </Portal>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
      {children}
    </div>
  );
}

// The parse confidence, straight from the stored element — the same number the
// review flow and the flag eval act on, surfaced next to the source it grades.
function ConfidenceBar({ value, rev }: { value: number; rev: boolean }) {
  const pct = Math.round(value * 100);
  return (
    <div
      className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium ${
        rev
          ? "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
          : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
      }`}
    >
      {rev ? (
        <AlertTriangle size={14} className="shrink-0" />
      ) : (
        <BadgeCheck size={14} className="shrink-0" />
      )}
      <span className="shrink-0">Parse confidence</span>
      <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-black/10 dark:bg-white/15">
        <span
          className="absolute inset-y-0 left-0 rounded-full bg-current"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="shrink-0 font-mono tabular-nums">{pct}%</span>
    </div>
  );
}
