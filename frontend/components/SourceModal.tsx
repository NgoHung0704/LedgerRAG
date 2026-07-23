"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ExternalLink } from "lucide-react";
import {
  elementImageUrl,
  getElement,
  pageImageUrl,
  type Citation,
  type ElementDetail,
} from "@/lib/api";
import { Modal, Spinner } from "@/components/ui";

/** Citation click-through: parsed table HTML side by side with the ORIGINAL
 * crop image (principle #3 — the trace back to the source is always there). */
export default function SourceModal({
  citation,
  onClose,
}: {
  citation: Citation;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<ElementDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getElement(citation.element_id)
      .then(setDetail)
      .catch(() => setFailed(true));
  }, [citation.element_id]);

  return (
    <Modal
      title={`[${citation.index}] ${citation.filename} — page ${citation.page}`}
      onClose={onClose}
      wide
    >
      {citation.needs_review && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-medium">
              This source could not be parsed reliably.
            </div>
            <div className="mt-0.5 text-[13px]">
              The original image below is authoritative — the assistant will not
              assert numbers from this table.
            </div>
          </div>
        </div>
      )}

      {failed ? (
        <p className="text-sm text-red-600 dark:text-red-400">Could not load source details.</p>
      ) : detail === null ? (
        <div className="flex justify-center py-10">
          <Spinner size={20} />
        </div>
      ) : (
        <div className="space-y-4">
          {detail.table?.summary && (
            <p className="text-[13px] italic leading-5 text-slate-500 dark:text-slate-400">
              {detail.table.summary}
            </p>
          )}

          {detail.table?.html && !citation.needs_review && (
            <div>
              <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
                Parsed table ({detail.table.parse_strategy})
              </div>
              <div
                className="doc-table max-h-72 overflow-auto rounded-lg border border-slate-200 p-2 dark:border-slate-700"
                dangerouslySetInnerHTML={{ __html: detail.table.html }}
              />
            </div>
          )}

          {detail.type === "text" && citation.snippet && (
            <blockquote className="border-l-2 border-slate-200 pl-3 text-sm leading-6 text-slate-600 dark:border-slate-700 dark:text-slate-300">
              {citation.snippet}
              {citation.snippet.length >= 240 && "…"}
            </blockquote>
          )}

          <div>
            <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
              Original from the document
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={elementImageUrl(detail.id)}
              alt={`Original of ${citation.filename} page ${citation.page}`}
              className="max-h-[45vh] w-full rounded-lg border border-slate-200 bg-white object-contain dark:border-slate-700"
            />
          </div>

          <a
            href={pageImageUrl(citation.doc_id, citation.page)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-300"
          >
            <ExternalLink size={13} /> Open full page {citation.page}
          </a>
        </div>
      )}
    </Modal>
  );
}
