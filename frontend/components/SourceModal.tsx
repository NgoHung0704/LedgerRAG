"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  ExternalLink,
  FileText,
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
import { Spinner } from "@/components/ui";

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

  // slide in on mount; lock the page behind the drawer while it is open
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true));
    document.body.style.overflow = "hidden";
    return () => {
      cancelAnimationFrame(id);
      document.body.style.overflow = "";
    };
  }, []);

  // animate out, THEN let the parent unmount us
  const close = () => {
    setShown(false);
    setTimeout(onClose, 300);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rev = citation.needs_review;
  const conf = detail?.confidence;

  return (
    <div className="fixed inset-0 z-50">
      <div
        onClick={close}
        className={`absolute inset-0 bg-slate-900/40 transition-opacity duration-300 ${
          shown ? "opacity-100" : "opacity-0"
        }`}
      />
      <aside
        role="dialog"
        aria-label={`Source ${citation.index}`}
        className={`absolute right-0 top-0 flex h-full w-[440px] max-w-[92vw] flex-col border-l border-slate-200 bg-white shadow-xl transition-transform duration-300 ease-out dark:border-slate-800 dark:bg-[#171d24] ${
          shown ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* header */}
        <div className="flex items-start gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
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
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Source [{citation.index}]
            </div>
            <div className="truncate font-serif text-[15px] font-semibold text-slate-900 dark:text-slate-100">
              {citation.filename}
            </div>
            <div className="font-mono text-xs text-slate-500 dark:text-slate-400">
              page {citation.page}
              {citation.kind === "table" ? " · tableau" : ""}
            </div>
          </div>
          <button
            onClick={close}
            aria-label="Fermer"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            <X size={18} />
          </button>
        </div>

        {/* body */}
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {conf != null && <ConfidenceBar value={conf} rev={rev} />}

          {rev && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <div>
                <div className="font-medium">Parse peu fiable — aucun chiffre affirmé.</div>
                <div className="mt-0.5 text-[13px]">
                  L’image ci-dessous fait foi ; l’assistant n’affirme jamais un
                  nombre depuis ce tableau.
                </div>
              </div>
            </div>
          )}

          {failed ? (
            <p className="text-sm text-red-600 dark:text-red-400">
              Impossible de charger la source.
            </p>
          ) : detail === null ? (
            <div className="flex justify-center py-10">
              <Spinner size={20} />
            </div>
          ) : (
            <>
              {detail.table?.summary && (
                <p className="text-[13px] italic leading-5 text-slate-500 dark:text-slate-400">
                  {detail.table.summary}
                </p>
              )}

              {detail.table?.html && !rev && (
                <div>
                  <SectionLabel>
                    Tableau analysé
                    {detail.table.parse_strategy
                      ? ` (${detail.table.parse_strategy})`
                      : ""}
                  </SectionLabel>
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
                <SectionLabel>Original du document</SectionLabel>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={elementImageUrl(detail.id)}
                  alt={`Original de ${citation.filename} page ${citation.page}`}
                  className="w-full rounded-lg border border-slate-200 bg-white object-contain dark:border-slate-700"
                />
              </div>
            </>
          )}
        </div>

        {/* footer */}
        <div className="border-t border-slate-100 px-5 py-3.5 dark:border-slate-800">
          <a
            href={pageImageUrl(citation.doc_id, citation.page)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-300"
          >
            <ExternalLink size={13} /> Ouvrir la page {citation.page} en entier
          </a>
        </div>
      </aside>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
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
      <span className="shrink-0">Confiance du parse</span>
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
