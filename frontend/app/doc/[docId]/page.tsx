"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  FileText,
  Image as ImageIcon,
  Pencil,
  RefreshCw,
  ScanText,
  Table2,
} from "lucide-react";
import ElementEditor from "@/components/ElementEditor";
import {
  API_URL,
  approveElement,
  getDocumentView,
  markElementUnusable,
  type DocumentView,
  type ElementView,
  type RecordPreview,
} from "@/lib/api";
import { Button, Card, Spinner, StatusPill } from "@/components/ui";

/** Document Inspector: everything ingestion produced, element by element.
 * Tables show all three stored representations — HTML (display), records
 * (dimensions/metrics/raw_values, what the chat quotes numbers from) and the
 * routing summary — next to the ORIGINAL crop image (principle #3). */
export default function DocPage({ params }: { params: { docId: string } }) {
  const [view, setView] = useState<DocumentView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    () =>
      getDocumentView(params.docId)
        .then(setView)
        .catch((e) => setError(String(e))),
    [params.docId],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  // live-refresh while the document is still being processed
  const processing =
    view !== null && !["done", "failed"].includes(view.document.status);
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [processing, refresh]);

  if (error) {
    return <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>;
  }
  if (view === null) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size={22} />
      </div>
    );
  }

  const { document: doc, elements } = view;
  const pages = Array.from(new Set(elements.map((e) => e.page))).sort(
    (a, b) => a - b,
  );
  const tables = elements.filter((e) => e.type === "table").length;

  return (
    <div>
      <Link
        href={`/kb/${doc.kb_id}`}
        className="mb-2 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600"
      >
        <ArrowLeft size={13} /> Back to knowledge base
      </Link>

      <div className="mb-1 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{doc.filename}</h1>
        <StatusPill status={doc.status} />
        {processing && (
          <span className="inline-flex items-center gap-1 text-xs text-slate-400">
            <RefreshCw size={12} className="animate-spin" /> refreshing…
          </span>
        )}
      </div>
      <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
        {doc.page_count ?? "—"} pages · {elements.length} elements · {tables}{" "}
        table{tables === 1 ? "" : "s"} — tables are stored as{" "}
        <span className="font-medium text-slate-600 dark:text-slate-300">
          HTML + records (JSON) + summary
        </span>
        , never flattened to markdown.
      </p>

      {doc.status === "failed" && doc.error && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          {doc.error}
        </div>
      )}

      {elements.length === 0 ? (
        <Card className="p-8 text-center text-sm text-slate-500 dark:text-slate-400">
          {doc.status === "done"
            ? "Ingestion produced no elements for this document."
            : "No parsed elements yet — ingestion is still running."}
        </Card>
      ) : (
        pages.map((page) => (
          <section key={page} className="mb-8">
            <div className="mb-3 flex items-center gap-3">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                Page {page}
              </h2>
              <a
                href={`${API_URL}/api/documents/${doc.id}/pages/${page}/image`}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-indigo-600 hover:text-indigo-500"
              >
                view page image
              </a>
              <div className="h-px flex-1 bg-slate-200" />
            </div>
            <div className="space-y-4">
              {elements
                .filter((e) => e.page === page)
                .map((element) => (
                  <ElementCard
                    key={element.id}
                    element={element}
                    onChanged={refresh}
                  />
                ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}

const TYPE_META = {
  text: { icon: FileText, label: "Text" },
  table: { icon: Table2, label: "Table" },
  figure: { icon: ImageIcon, label: "Figure" },
} as const;

function ElementCard({
  element,
  onChanged,
}: {
  element: ElementView;
  onChanged: () => void;
}) {
  const { icon: Icon, label } = TYPE_META[element.type];
  const [showOriginal, setShowOriginal] = useState(
    element.type !== "text" || element.needs_review,
  );
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const review = async (action: "approve" | "unusable") => {
    setReviewBusy(true);
    setReviewError(null);
    try {
      if (action === "approve") await approveElement(element.id);
      else await markElementUnusable(element.id);
      onChanged();
    } catch (e) {
      setReviewError(String(e));
    } finally {
      setReviewBusy(false);
    }
  };

  const signals = element.confidence_detail?.signals;

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 bg-slate-50/60 px-4 py-2 dark:border-slate-800 dark:bg-slate-800/40">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200">
          <Icon size={14} /> {label}
        </span>
        {element.table?.parse_strategy && (
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300">
            {element.table.parse_strategy}
          </span>
        )}
        {element.ocr && (
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">
            <ScanText size={11} /> OCR
          </span>
        )}
        {element.confidence !== null && (
          <span className="text-[11px] text-slate-400">
            confidence {Math.round(element.confidence * 100)}%
          </span>
        )}
        {element.needs_review && (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-amber-200">
            <AlertTriangle size={11} /> needs review
          </span>
        )}
        {element.unusable && (
          <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-600">
            excluded from retrieval
          </span>
        )}
        {element.span_pages && element.span_pages.length > 1 && (
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 ring-1 ring-blue-200">
            spans pages {element.span_pages.join("–")}
          </span>
        )}
        {element.edited && (
          <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
            edited
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {element.type !== "figure" && (
            <button
              onClick={() => setEditing(true)}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 hover:text-indigo-500"
            >
              <Pencil size={12} /> edit
            </button>
          )}
          <button
            onClick={() => setShowOriginal((v) => !v)}
            className="text-[11px] font-medium text-slate-500 hover:text-slate-700"
          >
            {showOriginal ? "hide original image" : "show original image"}
          </button>
        </div>
      </div>

      {editing && (
        <ElementEditor
          elementId={element.id}
          onClose={() => setEditing(false)}
          onSaved={onChanged}
        />
      )}

      <div className="space-y-4 p-4">
        {element.parse_error && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Parse failed honestly: {element.parse_error} — the original image
            below is the authoritative source.
          </div>
        )}

        {/* Phase 3: confidence signals + review actions */}
        {signals && (
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
            <span className="font-medium uppercase tracking-wide text-slate-400">
              confidence signals:
            </span>
            {Object.entries(signals).map(([name, score]) => (
              <span
                key={name}
                className={`rounded-full px-2 py-0.5 font-medium ${
                  score >= 0.98
                    ? "bg-emerald-50 text-emerald-700"
                    : score >= 0.9
                      ? "bg-amber-50 text-amber-700"
                      : "bg-red-50 text-red-700"
                }`}
              >
                {name} {(score * 100).toFixed(0)}%
              </span>
            ))}
          </div>
        )}

        {element.needs_review && !element.unusable && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2.5">
            <span className="mr-auto text-xs text-amber-800">
              Review this parse against the original image, then decide:
            </span>
            <Button
              variant="secondary"
              className="!py-1.5 text-xs"
              disabled={reviewBusy}
              onClick={() => review("approve")}
            >
              Approve — parse is correct
            </Button>
            <Button
              variant="secondary"
              className="!py-1.5 text-xs !text-red-600"
              disabled={reviewBusy}
              onClick={() => review("unusable")}
            >
              Mark unusable
            </Button>
            {reviewError && (
              <span className="w-full text-xs text-red-600">{reviewError}</span>
            )}
          </div>
        )}

        {/* text */}
        {element.type === "text" && element.text_preview && (
          <div>
            <SectionLabel>
              Extracted text · {element.chunk_count} chunk
              {element.chunk_count === 1 ? "" : "s"} indexed
            </SectionLabel>
            <p className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-[13px] leading-6 text-slate-700 dark:bg-slate-800/50 dark:text-slate-300">
              {element.text_preview}
              {element.text_preview.length >= 600 && "…"}
            </p>
          </div>
        )}

        {/* figure */}
        {element.type === "figure" && element.caption && (
          <div>
            <SectionLabel>Caption</SectionLabel>
            <p className="text-[13px] italic text-slate-600">{element.caption}</p>
          </div>
        )}

        {/* table: the three representations */}
        {element.table && (
          <>
            {element.table.summary && (
              <div>
                <SectionLabel>Representation 3 — summary (routing)</SectionLabel>
                <p className="text-[13px] italic leading-5 text-slate-600 dark:text-slate-300">
                  {element.table.summary}
                </p>
              </div>
            )}
            {element.table.html && (
              <div>
                <SectionLabel>
                  Representation 1 — HTML ({element.table.n_rows ?? "?"}×
                  {element.table.n_cols ?? "?"}, display)
                </SectionLabel>
                <div
                  className="doc-table max-h-80 overflow-auto rounded-lg border border-slate-200 p-2 dark:border-slate-700"
                  dangerouslySetInnerHTML={{ __html: element.table.html }}
                />
              </div>
            )}
            {element.table.records_count > 0 && (
              <div>
                <SectionLabel>
                  Representation 2 — records ({element.table.records_count}{" "}
                  total, what answers quote numbers from)
                </SectionLabel>
                <RecordsTable records={element.table.records_preview} />
                {element.table.records_count >
                  element.table.records_preview.length && (
                  <p className="mt-1 text-[11px] text-slate-400">
                    showing first {element.table.records_preview.length} of{" "}
                    {element.table.records_count}
                  </p>
                )}
              </div>
            )}
          </>
        )}

        {/* original crop — the trace back to the source, always available */}
        {showOriginal && (
          <div>
            <SectionLabel>Original from the document</SectionLabel>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${API_URL}${element.crop_url}`}
              alt="original crop"
              className="max-h-96 rounded-lg border border-slate-200 bg-white object-contain dark:border-slate-700"
            />
          </div>
        )}
      </div>
    </Card>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
      {children}
    </div>
  );
}

function RecordsTable({ records }: { records: RecordPreview[] }) {
  if (records.length === 0) return null;
  const dimKeys = Object.keys(records[0].dimensions);
  const metricKeys = Object.keys(records[0].metrics);
  return (
    <div className="max-h-72 overflow-auto rounded-lg border border-slate-200 dark:border-slate-700">
      <table className="w-full text-[12px]">
        <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
          <tr>
            {dimKeys.map((k) => (
              <th key={k} className="border-b border-slate-200 px-2.5 py-1.5 text-left font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
                {k}
              </th>
            ))}
            {metricKeys.map((k) => (
              <th key={k} className="border-b border-slate-200 px-2.5 py-1.5 text-right font-semibold text-indigo-600 dark:border-slate-700 dark:text-indigo-300">
                {k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {records.map((r, i) => (
            <tr key={i} className="odd:bg-white even:bg-slate-50/50 dark:odd:bg-transparent dark:even:bg-slate-800/40">
              {dimKeys.map((k) => (
                <td key={k} className="px-2.5 py-1 text-slate-700 dark:text-slate-300">
                  {String(r.dimensions[k] ?? "")}
                </td>
              ))}
              {metricKeys.map((k) => (
                <td key={k} className="px-2.5 py-1 text-right tabular-nums text-slate-800 dark:text-slate-200"
                    title={`normalized: ${r.metrics[k] ?? "null"}`}>
                  {r.raw_values[k] ?? String(r.metrics[k] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
