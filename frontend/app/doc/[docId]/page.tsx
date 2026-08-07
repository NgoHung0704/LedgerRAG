"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  ArrowLeft,
  Columns3,
  Combine,
  Eraser,
  ExternalLink,
  FileDown,
  FileText,
  Image as ImageIcon,
  Pencil,
  RefreshCw,
  Rows3,
  ScanSearch,
  ScanText,
  SplitSquareVertical,
  Table2,
  TableCellsMerge,
  Trash2,
  Undo2,
} from "lucide-react";
import BoilerplatePanel from "@/components/BoilerplatePanel";
import ElementEditor, { type ElementProposal } from "@/components/ElementEditor";
import RecordsTable from "@/components/RecordsTable";
import {
  API_URL,
  approveElement,
  convertElementToText,
  deleteElement,
  deletePage,
  documentExportUrl,
  documentOriginalUrl,
  getDocumentView,
  getElement,
  markElementUnusable,
  recheckElement,
  rereadElement,
  setElementRowMerging,
  mergeElementTables,
  splitElementTable,
  undoElementEdit,
  type DocumentView,
  type ElementDetail,
  type ElementView,
  type RereadMode,
} from "@/lib/api";
import { Button, Card, Spinner, StatusPill, linkButtonCls } from "@/components/ui";
import { confirm } from "@/components/confirm";

/** Document Inspector: everything ingestion produced, element by element.
 * Tables show all three stored representations — HTML (display), records
 * (dimensions/metrics/raw_values, what the chat quotes numbers from) and the
 * routing summary — next to the ORIGINAL crop image (principle #3). */
export default function DocPage({ params }: { params: { docId: string } }) {
  const [view, setView] = useState<DocumentView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [deletingPage, setDeletingPage] = useState<number | null>(null);
  // the element Review sent us to: scrolled to, then ringed so it is obvious
  // WHICH one on a page holding a dozen
  const [target, setTarget] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  // tables the reviewer has picked to join. Which ones is their decision: this
  // used to join with "the next table in reading order", which nobody could
  // see, so nobody could tell what they were about to get.
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [joining, setJoining] = useState(false);
  const jumped = useRef(false);

  const removePage = async (page: number) => {
    if (
      !(await confirm({
        title: `Delete everything parsed from page ${page}?`,
        message:
          "Its text, tables and vectors go, and answers stop citing them. The " +
          "original file is untouched — Reprocess brings the page back.",
        confirmLabel: `Delete page ${page}`,
      }))
    )
      return;
    setDeletingPage(page);
    try {
      await deletePage(params.docId, page);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setDeletingPage(null);
    }
  };

  const togglePick = (id: string) =>
    setPicked((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const joinPicked = async () => {
    const ids = Array.from(picked);
    if (
      !(await confirm({
        title: `Join ${ids.length} tables into one?`,
        message:
          "They are read again together as a single table, in document order. " +
          "The first one keeps its identity and undo restores it; the others " +
          "come back only by reprocessing the document.",
        confirmLabel: "Join",
        danger: false,
      }))
    )
      return;
    setJoining(true);
    setError(null);
    try {
      await mergeElementTables(ids);
      setPicked(new Set());
      await refresh();
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setJoining(false);
    }
  };

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

  // Review links here with #el-<id>, and the browser resolves that fragment
  // while this page is still empty — the elements only arrive with the fetch
  // above. So the native jump did nothing and the reviewer landed at the top
  // of the document to hunt for the page themselves. Do the jump ourselves,
  // once, when the content it names actually exists.
  useEffect(() => {
    if (!view || jumped.current) return;
    const anchor = window.location.hash.slice(1);
    if (!anchor) return;
    jumped.current = true;
    const node = window.document.getElementById(anchor);
    if (!node) {
      // the queue outlived what it points at: the element was deleted, or the
      // document was reprocessed and its elements have new ids
      setStale(anchor.startsWith("el-"));
      return;
    }
    node.scrollIntoView({ block: "start", behavior: "smooth" });
    if (anchor.startsWith("el-")) setTarget(anchor.slice(3));
  }, [view]);

  // let the ring go once it has been seen, so it never reads as a lasting
  // property of the element
  useEffect(() => {
    if (!target) return;
    const t = setTimeout(() => setTarget(null), 3000);
    return () => clearTimeout(t);
  }, [target]);

  if (error) {
    return <div className="callout callout-danger">{error}</div>;
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
      {/* the document's identity and its actions stay put while the pages
          scroll: negative margins cover the container's padding so nothing
          slides out from behind it */}
      <div className="sticky top-0 z-20 -mx-4 -mt-5 mb-4 border-b border-line bg-canvas/95 px-4 pb-3 pt-5 backdrop-blur sm:-mx-6 sm:-mt-6 sm:px-6 sm:pt-6">
        <Link
          href={`/kb/${doc.kb_id}`}
          className="mb-2 inline-flex items-center gap-1 text-xs text-ink-subtle hover:text-ink-muted"
        >
          <ArrowLeft size={13} /> Back to knowledge base
        </Link>

        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">
            {doc.filename}
          </h1>
          <StatusPill status={doc.status} />
          {processing && (
            <span className="inline-flex items-center gap-1 text-xs text-ink-subtle">
              <RefreshCw size={12} className="animate-spin" /> refreshing…
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            {picked.size > 0 && (
              // the one action the current selection is FOR, so it carries the
              // accent while the standing tools beside it stay outlined
              <Button
                size="sm"
                variant="primary"
                onClick={joinPicked}
                disabled={picked.size < 2}
                loading={joining}
                icon={<Combine size={13} />}
                className="rise"
                title={
                  picked.size < 2
                    ? "Pick a second table to join this one with"
                    : "Read the picked tables again as one table, in document order"
                }
              >
                {joining
                  ? "joining…"
                  : `Join ${picked.size} table${picked.size === 1 ? "" : "s"}`}
              </Button>
            )}
            <Button
              size="sm"
              variant="tonal"
              icon={<Eraser size={13} />}
              onClick={() => setScanning(true)}
            >
              Detect boilerplate
            </Button>
            <a
              href={documentExportUrl(doc.id)}
              download
              title="Everything ingestion produced, as plain text: the stored HTML, the records, and the chunks exactly as indexed."
              className={linkButtonCls}
            >
              <FileDown size={13} /> Export parse
            </a>
            <a
              href={documentOriginalUrl(doc.id)}
              target="_blank"
              rel="noreferrer"
              className={linkButtonCls}
            >
              <ExternalLink size={13} /> Open original document
            </a>
          </div>
        </div>

        <p className="mt-0.5 text-sm text-ink-muted">
          {doc.page_count ?? "—"} pages · {elements.length} elements · {tables}{" "}
          table{tables === 1 ? "" : "s"} — tables are stored as{" "}
          <span className="font-medium text-ink-muted">
            HTML + records (JSON) + summary
          </span>
          , never flattened to markdown.
        </p>
      </div>

      {scanning && (
        <BoilerplatePanel
          docId={doc.id}
          onClose={() => setScanning(false)}
          onExcluded={refresh}
        />
      )}

      {doc.status === "failed" && doc.error && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          {doc.error}
        </div>
      )}

      {stale && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          That element is no longer in this document — it was deleted, or the
          document was reprocessed and its elements were parsed afresh. The
          pages below are what is stored now.
        </div>
      )}

      {elements.length === 0 ? (
        <Card className="p-8 text-center text-sm text-ink-muted">
          {doc.status === "done"
            ? "Ingestion produced no elements for this document."
            : "No parsed elements yet — ingestion is still running."}
        </Card>
      ) : (
        pages.map((page) => (
          // scroll-mt clears the sticky header: without it an anchor jump puts
          // the target UNDER the bar it just scrolled past
          <section key={page} id={`page-${page}`} className="mb-8 scroll-mt-36">
            <div className="group mb-3 flex items-center gap-3">
              <h2 className="text-sm font-semibold text-ink">
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
              <button
                onClick={() => removePage(page)}
                disabled={deletingPage === page}
                title="Drop everything parsed from this page. The original file is untouched, so Reprocess brings it back."
                className="inline-flex items-center gap-1 text-xs text-ink-subtle opacity-0 transition-opacity hover:text-red-600 focus:opacity-100 disabled:opacity-50 group-hover:opacity-100"
              >
                {deletingPage === page ? (
                  <Spinner size={11} />
                ) : (
                  <Trash2 size={12} />
                )}
                delete page
              </button>
              <div className="h-px flex-1 bg-line" />
            </div>
            <div className="space-y-4">
              {elements
                .filter((e) => e.page === page)
                .map((element) => (
                  <ElementCard
                    key={element.id}
                    element={element}
                    highlighted={target === element.id}
                    picked={picked.has(element.id)}
                    onPick={() => togglePick(element.id)}
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
  highlighted = false,
  picked = false,
  onPick,
}: {
  element: ElementView;
  onChanged: () => void;
  /** this is the element a Review link pointed at */
  highlighted?: boolean;
  /** picked for joining with other tables */
  picked?: boolean;
  onPick?: () => void;
}) {
  const { icon: Icon, label } = TYPE_META[element.type];
  const [showOriginal, setShowOriginal] = useState(
    element.type !== "text" || element.needs_review,
  );
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  // lazy full content (getElement returns the WHOLE text + all records); the
  // list view only ships a preview, so we fetch on demand to expand
  const [detail, setDetail] = useState<ElementDetail | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [showFullText, setShowFullText] = useState(false);
  const [showAllRecords, setShowAllRecords] = useState(false);
  // a model proposal offered for review before it replaces anything
  const [proposed, setProposed] = useState<ElementProposal | undefined>();
  const [rechecking, setRechecking] = useState(false);
  const [rereading, setRereading] = useState(false);
  const [rereadMenu, setRereadMenu] = useState(false);
  const [converting, setConverting] = useState(false);
  const [splitting, setSplitting] = useState(false);
  const [unmerging, setUnmerging] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [undoing, setUndoing] = useState(false);
  const [removing, setRemoving] = useState(false);

  // The lazily fetched full content must not outlive the element it came from.
  // After an edit the card gets fresh props, but a cached `detail` would keep
  // displaying the very text that was just replaced — the card said "edited"
  // while still showing the old parse. Drop it whenever the content changes,
  // and collapse the expanders so the new preview is what's on screen.
  const contentVersion = `${element.edited}|${element.chunk_count}|${
    element.text_preview ?? ""
  }|${element.table?.records_count ?? 0}`;
  useEffect(() => {
    setDetail(null);
    setShowFullText(false);
    setShowAllRecords(false);
  }, [contentVersion]);

  const recheck = async () => {
    setRechecking(true);
    setReviewError(null);
    try {
      const r = await recheckElement(element.id);
      const pct = (v: number) => `${Math.round(v * 100)}%`;
      const agreement = r.signals?.agreement;
      setProposed({
        html: r.html,
        records: r.records,
        note:
          (r.stitched
            ? "Re-read from the stitched crop (this table spans pages, so it " +
              "cannot be re-rendered from one)"
            : `Re-read at ${r.dpi} dpi`) +
          (r.grid_hint ? " with the text-layer grid" : "") +
          (r.second_read
            ? `, then checked against the image — ${
                r.clean
                  ? "the check found no fault"
                  : `agreement ${
                      agreement === undefined ? "(not scored)" : pct(agreement)
                    }`
              }`
            : ", once (the check produced nothing usable, so the first read stands)") +
          `. Confidence ${pct(r.confidence)}.` +
          (r.error ? ` Parse reported: ${r.error}.` : "") +
          (r.findings && !r.clean ? `

${r.findings}` : ""),
      });
      setEditing(true);
    } catch (e) {
      setReviewError(String(e));
    } finally {
      setRechecking(false);
    }
  };

  const remove = async () => {
    if (
      !(await confirm({
        title: "Delete this element?",
        message:
          "Its chunks, records and vectors go with it, so answers stop citing " +
          "it. The original file is untouched — Reprocess brings it back.",
        confirmLabel: "Delete",
      }))
    )
      return;
    setRemoving(true);
    setReviewError(null);
    try {
      await deleteElement(element.id);
      onChanged();
    } catch (e) {
      setReviewError(String(e));
      setRemoving(false);
    }
  };

  // a value printed once against several rows is drawn as a merged cell,
  // which is what the page looks like — but a merged cell is harder to scan
  // across and hides how many rows it covers, so it is the reviewer's choice
  const rowsMerged = /rowspan=/i.test(element.table?.html ?? "");

  const toggleRowMerging = async () => {
    setUnmerging(true);
    setReviewError(null);
    setNotice(null);
    try {
      const result = await setElementRowMerging(element.id, !rowsMerged);
      setNotice(
        rowsMerged
          ? "Merged rows split — each row now carries its own value."
          : "Repeated values merged.",
      );
      onChanged();
      setDetail(result);
    } catch (e) {
      setReviewError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setUnmerging(false);
    }
  };

  const splitTable = async () => {
    if (
      !(await confirm({
        title: "Are these two tables?",
        message:
          "The model is asked only where the seam is; each part is then " +
          "re-parsed on its own and gets its own crop. Undo puts the single " +
          "table back.",
        confirmLabel: "Split",
        danger: false,
      }))
    )
      return;
    setSplitting(true);
    setReviewError(null);
    setNotice(null);
    try {
      const result = await splitElementTable(element.id);
      // say so out loud: a refusal and a success both used to leave the card
      // looking untouched, so there was no telling which had happened
      setNotice(`Split into ${result.parts} tables — ${result.reason}.`);
      onChanged();
      setDetail(result);
    } catch (e) {
      setReviewError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setSplitting(false);
    }
  };

  const undo = async () => {
    setUndoing(true);
    setReviewError(null);
    try {
      const detail = await undoElementEdit(element.id);
      onChanged();
      setDetail(detail);
    } catch (e) {
      setReviewError(String(e));
    } finally {
      setUndoing(false);
    }
  };

  const convertToText = async () => {
    if (
      !(await confirm({
        title: "Treat this as plain text?",
        message:
          "The cells' words become the text; the grid and its records are " +
          "dropped. Undo puts the table back, and so does reprocessing the " +
          "document if detection was right after all.",
        confirmLabel: "Convert to text",
        danger: false,
      }))
    )
      return;
    setConverting(true);
    setReviewError(null);
    try {
      await convertElementToText(element.id);
      onChanged();
    } catch (e) {
      setReviewError(String(e));
    } finally {
      setConverting(false);
    }
  };

  const reread = async (mode: RereadMode) => {
    setRereadMenu(false);
    setRereading(true);
    setReviewError(null);
    try {
      const { text } = await rereadElement(element.id, mode);
      setProposed({ text });
      setEditing(true);
    } catch (e) {
      setReviewError(String(e));
    } finally {
      setRereading(false);
    }
  };

  const ensureDetail = async () => {
    if (detail || detailBusy) return;
    setDetailBusy(true);
    try {
      setDetail(await getElement(element.id));
    } finally {
      setDetailBusy(false);
    }
  };

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
    // NOT overflow-hidden: the re-read menu drops out of the header, and on a
    // short element it is taller than the card. It also has to paint over the
    // cards below it, which come later in the DOM — hence the raised z while
    // it is open. The header rounds its own top corners instead.
    <Card
      id={`el-${element.id}`}
      className={`relative scroll-mt-36 transition-shadow duration-500 ${
        rereadMenu ? "z-30" : ""
      } ${
        highlighted
          ? // the accent, not a warning colour: this ring means "the element
            // you asked for is here", not "something is wrong with it". The
            // offset follows the ground token instead of a hex left over from
            // an older palette.
            "ring-2 ring-indigo-500 ring-offset-2 ring-offset-canvas"
          : ""
      }`}
    >
      <div className="flex flex-wrap items-center gap-2 rounded-t-xl border-b border-line bg-surface-sunken px-4 py-2">
        {element.type === "table" && onPick && (
          <label
            title="Pick this table to join it with another"
            className="inline-flex cursor-pointer items-center"
          >
            <input
              type="checkbox"
              checked={picked}
              onChange={onPick}
              className="h-3.5 w-3.5 cursor-pointer accent-indigo-600"
            />
          </label>
        )}
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink">
          <Icon size={14} /> {label}
        </span>
        {element.table?.parse_strategy && (
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300">
            {element.table.parse_strategy}
          </span>
        )}
        {element.ocr && (
          <span className="inline-flex items-center gap-1 rounded-full bg-surface-sunken px-2 py-0.5 text-[11px] font-medium text-ink-muted">
            <ScanText size={11} /> OCR
          </span>
        )}
        {element.confidence !== null && (
          <span className="text-[11px] text-ink-subtle">
            confidence {Math.round(element.confidence * 100)}%
          </span>
        )}
        {element.needs_review && (
          <span className="pill pill-warn">
            <AlertTriangle size={11} /> needs review
          </span>
        )}
        {element.layout_suspect && (
          <span
            title="This page lays its text out in columns (a slide or diagram). The words are right, but their order is not — re-read it to keep each column together."
            className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-700 ring-1 ring-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:ring-sky-800/60"
          >
            <Columns3 size={11} /> column layout
          </span>
        )}
        {element.unusable && (
          <span className="rounded-full bg-surface-sunken px-2 py-0.5 text-[11px] font-medium text-ink-muted">
            excluded from retrieval
          </span>
        )}
        {element.span_pages && element.span_pages.length > 1 && (
          <span className="pill pill-info">
            spans pages {element.span_pages.join("–")}
          </span>
        )}
        {element.edited && (
          <span className="pill pill-ok">
            edited
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {element.type === "text" && (
            <div className="relative">
              <button
                onClick={() => setRereadMenu((v) => !v)}
                disabled={rereading}
                title="Have the parser model read this page again from its image. You review the result before it replaces anything."
                className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 hover:text-indigo-500 disabled:opacity-50"
              >
                {rereading ? <Spinner size={11} /> : <ScanText size={12} />}
                {rereading ? "re-reading…" : "re-read with the VLM"}
              </button>
              {rereadMenu && !rereading && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setRereadMenu(false)}
                  />
                  <div className="pop absolute right-0 z-20 mt-1 w-72 origin-top-right rounded-lg border border-line bg-surface p-1.5 shadow-lift">
                    {(
                      [
                        {
                          mode: "structure",
                          label: "Structure",
                          hint: "Faithful transcription — a grid or diagram becomes a markdown table, so each column keeps its heading.",
                        },
                        {
                          mode: "summary",
                          label: "What the page says",
                          hint: "Prose explanation making the relations explicit. Useful when the layout carries the meaning.",
                        },
                        {
                          mode: "both",
                          label: "Structure + summary",
                          hint: "The transcription, then a few sentences reading it back.",
                        },
                      ] as const
                    ).map(({ mode, label, hint }) => (
                      <button
                        key={mode}
                        onClick={() => reread(mode)}
                        className="block w-full rounded px-2.5 py-2 text-left hover:bg-surface-sunken"
                      >
                        <span className="block text-[12px] font-medium text-ink">
                          {label}
                        </span>
                        <span className="block text-[11px] leading-4 text-ink-subtle">
                          {hint}
                        </span>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
          {element.type === "table" && (
            <Button
              size="xs"
              variant="tonal"
              onClick={recheck}
              loading={rechecking}
              icon={<ScanSearch size={12} />}
              title="Parse this table again at double the resolution, with the text-layer grid as a hint, and read it twice so the two reads can be compared. You review the result before it replaces anything."
            >
              {rechecking ? "re-parsing…" : "double-check"}
            </Button>
          )}
          {element.type === "table" && (
            <Button
              size="xs"
              variant="ghost"
              onClick={toggleRowMerging}
              loading={unmerging}
              icon={<Rows3 size={12} />}
              title="A value printed once against several rows is drawn as one merged cell — what the page looks like. Split it and every row carries its own value, which is easier to scan across and to copy one row out of. Display only: the records already hold a value per row either way."
            >
              {unmerging
                ? "redrawing…"
                : rowsMerged
                  ? "split merged rows"
                  : "merge repeated rows"}
            </Button>
          )}
          {element.type === "table" && (
            <Button
              size="xs"
              variant="ghost"
              onClick={splitTable}
              loading={splitting}
              icon={<SplitSquareVertical size={12} />}
              title="Detection sometimes draws one box around two tables printed one under another. Read as one, their rows share a set of records and a question about the first can be answered from a row of the second."
            >
              {splitting ? "splitting…" : "two tables"}
            </Button>
          )}
          {element.type === "table" && (
            <Button
              size="xs"
              variant="ghost"
              onClick={convertToText}
              loading={converting}
              icon={<TableCellsMerge size={12} />}
              title="Detection sometimes fires on prose laid out in columns. This drops the grid and records and keeps the cells' words as text."
            >
              {converting ? "converting…" : "not a table"}
            </Button>
          )}
          {element.undo_steps > 0 && (
            <Button
              size="xs"
              variant="ghost"
              onClick={undo}
              loading={undoing}
              icon={<Undo2 size={12} />}
              title={
                `Put this element back the way it was before the last edit ` +
                `(${element.undo_steps} step${
                  element.undo_steps === 1 ? "" : "s"
                } kept). Reprocessing the document also undoes it, but re-runs ` +
                `the whole file and drops every other correction made to it.`
              }
            >
              {undoing ? "undoing…" : `undo (${element.undo_steps})`}
            </Button>
          )}
          {element.type !== "figure" && (
            <Button
              size="xs"
              variant="tonal"
              icon={<Pencil size={12} />}
              onClick={() => {
                setProposed(undefined);
                setEditing(true);
              }}
            >
              edit
            </Button>
          )}
          <Button
            size="xs"
            variant="ghost"
            onClick={remove}
            loading={removing}
            icon={<Trash2 size={12} />}
            className="hover:!bg-red-50 hover:!text-red-700 dark:hover:!bg-red-950/40 dark:hover:!text-red-400"
            title="Drop this element, its chunks, records and vectors. Reprocessing the document brings it back."
          >
            delete
          </Button>
          <Button
            size="xs"
            variant="ghost"
            icon={<ImageIcon size={12} />}
            aria-pressed={showOriginal}
            onClick={() => setShowOriginal((v) => !v)}
          >
            {showOriginal ? "hide original" : "show original"}
          </Button>
        </div>
      </div>

      {editing && (
        <ElementEditor
          elementId={element.id}
          proposed={proposed}
          onClose={() => {
            setEditing(false);
            setProposed(undefined);
          }}
          onSaved={onChanged}
        />
      )}

      <div className="space-y-4 p-4">
        {/* What the last action did, or why it did nothing. This used to live
            inside the needs_review box, so on a table that was NOT flagged
            every failure was swallowed silently — press a button, watch
            nothing happen, with no way to tell a refusal from a success. */}
        {reviewError && (
          <div className="callout callout-danger !px-3 !py-2 text-xs">
            {reviewError}
          </div>
        )}
        {notice && (
          <div className="callout !px-3 !py-2 text-xs">{notice}</div>
        )}

        {element.parse_error && (
          <div className="callout callout-warn !px-3 !py-2 text-xs">
            Parse failed honestly: {element.parse_error} — the original image
            below is the authoritative source.
          </div>
        )}

        {/* Phase 3: confidence signals + review actions */}
        {signals && (
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
            <span className="font-medium uppercase tracking-wide text-ink-subtle">
              confidence signals:
            </span>
            {Object.entries(signals).map(([name, score]) => (
              <span
                key={name}
                // Colour marks the two ends that need a decision — clean, or
                // low enough to distrust. The middle band stays neutral: the
                // percentage is right there, and painting "acceptable" in the
                // needs-review colour cries wolf on every ordinary parse.
                className={`rounded-full px-2 py-0.5 font-medium ${
                  score >= 0.98
                    ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                    : score >= 0.9
                      ? "bg-surface-sunken text-ink-muted"
                      : "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-300"
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
              size="sm"
              variant="tonal"
              disabled={reviewBusy}
              onClick={() => review("approve")}
            >
              Approve — parse is correct
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={reviewBusy}
              onClick={() => review("unusable")}
            >
              Mark unusable
            </Button>
          </div>
        )}

        {/* text */}
        {element.type === "text" && element.text_preview && (
          <div>
            <SectionLabel>
              Extracted text · {element.chunk_count} chunk
              {element.chunk_count === 1 ? "" : "s"} indexed
            </SectionLabel>
            <TextBody
              text={
                (showFullText && detail?.text
                  ? detail.text
                  : element.text_preview) +
                (!showFullText &&
                (element.text_preview.length >= 600 || element.chunk_count > 1)
                  ? "…"
                  : "")
              }
            />
            {(element.text_preview.length >= 600 || element.chunk_count > 1) && (
              <Button
                size="xs"
                variant="ghost"
                className="mt-1.5 !text-indigo-700 dark:!text-indigo-300"
                loading={detailBusy}
                aria-expanded={showFullText}
                onClick={async () => {
                  if (!showFullText) await ensureDetail();
                  setShowFullText((v) => !v);
                }}
              >
                {showFullText ? "Show less" : detailBusy ? "Loading…" : "Show full text"}
              </Button>
            )}
          </div>
        )}

        {/* figure: the caption is the document's own words, the description is
            the parser VLM's reading of the picture — never conflate the two */}
        {element.type === "figure" && element.caption && (
          <div>
            <SectionLabel>Caption</SectionLabel>
            <p className="text-[13px] italic text-ink-muted">{element.caption}</p>
          </div>
        )}
        {element.type === "figure" && element.description && (
          <div>
            <SectionLabel>
              Description{" "}
              <span className="font-normal normal-case tracking-normal text-ink-subtle">
                — read from the image by the parser model
                {element.decorative && ", judged decorative and not indexed"}
              </span>
            </SectionLabel>
            <p
              className={`whitespace-pre-wrap text-[13px] ${
                element.decorative ? "text-ink-subtle" : "text-ink-muted"
              }`}
            >
              {element.description}
            </p>
            {element.chart_check && (
              <p className="mt-1.5 text-[12px] text-ink-subtle">
                Bars measured from the PDF vs the values read off them:{" "}
                {element.chart_check}
              </p>
            )}
          </div>
        )}

        {/* table: the three representations */}
        {element.table && (
          <>
            {element.table.summary && (
              <div>
                <SectionLabel>Representation 3 — summary (routing)</SectionLabel>
                <p className="text-[13px] italic leading-5 text-ink-muted">
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
                  className="doc-table max-h-80 overflow-auto rounded-lg border border-line p-2"
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
                <RecordsTable
                  records={
                    showAllRecords && detail?.table?.records
                      ? detail.table.records
                      : element.table.records_preview
                  }
                />
                {element.table.records_count >
                  element.table.records_preview.length && (
                  <Button
                    size="xs"
                    variant="ghost"
                    className="mt-1.5 !text-indigo-700 dark:!text-indigo-300"
                    loading={detailBusy}
                    aria-expanded={showAllRecords}
                    onClick={async () => {
                      if (!showAllRecords) await ensureDetail();
                      setShowAllRecords((v) => !v);
                    }}
                  >
                    {showAllRecords
                      ? "Show fewer"
                      : detailBusy
                        ? "Loading…"
                        : `Show all ${element.table.records_count} records`}
                  </Button>
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
              className="max-h-96 max-w-full rounded-lg border border-line bg-surface object-contain"
            />
          </div>
        )}
      </div>
    </Card>
  );
}

/** Is this text actually marked up, or just text that happens to contain
 *  punctuation? A re-read in transcription mode hands back a markdown table or
 *  a heading structure; the original extraction is plain prose. Rendering the
 *  first as text shows the reader a wall of pipes and hashes, and rendering the
 *  second as markdown eats its line breaks — so the answer has to be decided
 *  per element rather than picked once. */
function looksLikeMarkdown(s: string): boolean {
  return (
    /^\s*\|.*\|\s*$/m.test(s) || // a table row
    /^\s{0,3}#{1,6}\s+\S/m.test(s) || // an ATX heading
    /^\s{0,3}([-*+]|\d+[.)])\s+\S/m.test(s) // a list item
  );
}

function TextBody({ text }: { text: string }) {
  const cls =
    "rounded-lg bg-surface-sunken p-3 text-[13px] leading-6 text-ink";
  if (!looksLikeMarkdown(text))
    return <p className={`whitespace-pre-wrap break-words ${cls}`}>{text}</p>;
  // a re-read can come back as a markdown TABLE — the only content here with
  // no width of its own, so it needs a scroller like every other table view
  return (
    <div
      className={`doc-table prose prose-sm max-w-none overflow-x-auto dark:prose-invert ${cls}`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
      {children}
    </div>
  );
}
