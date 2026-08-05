"use client";

import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Image as ImageIcon,
  Maximize2,
  Minimize2,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import { Portal } from "@/components/ui";
import {
  deriveFromHtml,
  editElement,
  elementImageUrl,
  getElement,
  type ElementDetail,
  type ElementEdit,
  type RecordEdit,
} from "@/lib/api";
import { Button, Spinner } from "@/components/ui";
import RecordsTable from "@/components/RecordsTable";
import EditAssistant from "@/components/EditAssistant";

type Tab = "text" | "html" | "records" | "summary";

/** Full-screen split editor: source on the left, live preview on the right, so
 * you edit the parsed text / table HTML / records and see the result as the app
 * renders it. On save the element is re-indexed so answers use the correction. */
/** A model's proposal offered for review: it pre-fills the panes instead of the
 * stored values, so it is compared against the original image and only becomes
 * the element's content when the reviewer saves. */
export type ElementProposal = {
  text?: string;
  html?: string;
  summary?: string;
  records?: RecordEdit[];
  note?: string; // e.g. how the two reads of a re-check agreed
};

export default function ElementEditor({
  elementId,
  onClose,
  onSaved,
  proposed,
}: {
  elementId: string;
  onClose: () => void;
  onSaved: () => void;
  proposed?: ElementProposal;
}) {
  const [detail, setDetail] = useState<ElementDetail | null>(null);
  const [text, setText] = useState("");
  const [html, setHtml] = useState("");
  const [summary, setSummary] = useState("");
  const [recordsJson, setRecordsJson] = useState("");
  const [tab, setTab] = useState<Tab>("text");
  const [busy, setBusy] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [deriving, setDeriving] = useState(false);
  const [derived, setDerived] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A proposal asks you to judge a re-reading against what is actually printed,
  // so the printed thing has to be HERE. It used to live only on the element
  // card behind this dialog, which meant closing the editor, hunting the page
  // for the card, and opening it again to check a single figure.
  const [showOriginal, setShowOriginal] = useState(Boolean(proposed));
  // How big you like this window is a working habit, not a per-element choice,
  // so it survives the dialog closing.
  const [maximised, setMaximised] = useState(false);
  useEffect(() => {
    try {
      setMaximised(localStorage.getItem("editor-max") === "1");
    } catch {
      /* storage disabled — the editor just starts windowed every time */
    }
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem("editor-max", maximised ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [maximised]);

  // Filling the screen removes the backdrop, and with it the click-outside way
  // out — so Escape has to work. It steps down one level at a time rather than
  // throwing away an edit on the first press.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (maximised) setMaximised(false);
      else onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [maximised, onClose]);

  useEffect(() => {
    getElement(elementId)
      .then((d) => {
        setDetail(d);
        setText(proposed?.text ?? d.text ?? "");
        setHtml(proposed?.html ?? d.table?.html ?? "");
        setSummary(proposed?.summary ?? d.table?.summary ?? "");
        setRecordsJson(
          JSON.stringify(proposed?.records ?? d.table?.records ?? [], null, 2),
        );
        // land on the pane the proposal is about
        setTab(proposed?.text ? "text" : d.table ? "html" : "text");
      })
      .catch((e) => setError(String(e)));
  }, [elementId, proposed]);

  const isTable = !!detail?.table;
  const tabs: { id: Tab; label: string }[] = isTable
    ? [
        { id: "html", label: "HTML" },
        { id: "records", label: "Records" },
        { id: "summary", label: "Summary" },
      ]
    : [{ id: "text", label: "Text" }];

  // live-parse the records JSON so the preview (and save) can flag errors early
  const records = useMemo<
    { ok: true; value: unknown[] } | { ok: false; error: string }
  >(() => {
    if (!recordsJson.trim()) return { ok: true, value: [] };
    try {
      const parsed = JSON.parse(recordsJson);
      if (!Array.isArray(parsed))
        return { ok: false, error: "records must be a JSON array" };
      return { ok: true, value: parsed };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  }, [recordsJson]);

  // Correcting the HTML alone leaves the element inconsistent: a right-looking
  // grid on screen while answers keep quoting the records built off the OLD
  // parse. This reads the records back out of the edited HTML and refreshes the
  // routing summary — still only a proposal, saved with everything else.
  const derive = async () => {
    setDeriving(true);
    setError(null);
    setDerived(null);
    try {
      const r = await deriveFromHtml(elementId, html);
      if (r.records.length > 0) {
        setRecordsJson(JSON.stringify(r.records, null, 2));
      }
      if (r.summary) setSummary(r.summary);
      setDerived(
        r.records.length > 0
          ? `Rebuilt ${r.records.length} records from a ${r.rows}×${r.cols} grid` +
              (r.summary ? " and refreshed the summary." : ".")
          : "No records could be read out of this HTML — the existing ones were kept. Check the header row.",
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setDeriving(false);
    }
  };

  const save = async () => {
    setError(null);
    const edit: ElementEdit = {};
    if (detail?.type === "text") edit.text = text;
    if (detail?.table) {
      if (!records.ok) {
        setError(`Records JSON is invalid: ${records.error}`);
        setTab("records");
        return;
      }
      edit.html = html;
      edit.summary = summary;
      edit.records = records.value as ElementEdit["records"];
    }
    setBusy(true);
    try {
      await editElement(elementId, edit);
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Portal>
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 ${
        maximised ? "p-0" : "p-3 sm:p-6"
      }`}
      onClick={onClose}
    >
      <div
        className={`flex w-full flex-col bg-surface text-ink shadow-2xl ${
          maximised
            ? "h-full max-h-none max-w-none rounded-none"
            : "h-full max-h-[92vh] max-w-6xl rounded-xl"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* header: title + tabs + close */}
        <div className="flex items-center gap-3 border-b border-line px-4 py-2.5">
          <h3 className="text-sm font-semibold">Edit parsed element</h3>
          <div className="flex gap-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  tab === t.id
                    ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
                    : "text-ink-muted hover:bg-surface-sunken"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => setAssistantOpen((v) => !v)}
            title="Ask the model to change the content you are editing. It rearranges what is there — it never adds figures — and you apply the result yourself."
            className={`ml-auto inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              assistantOpen
                ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
                : "text-ink-muted hover:bg-surface-sunken"
            }`}
          >
            <Sparkles size={13} /> Assistant
          </button>
          <button
            onClick={() => setShowOriginal((v) => !v)}
            aria-pressed={showOriginal}
            title="Show the original crop from the document beside the editor"
            className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              showOriginal
                ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
                : "text-ink-muted hover:bg-surface-sunken"
            }`}
          >
            <ImageIcon size={13} /> Original
          </button>
          <button
            onClick={() => setMaximised((v) => !v)}
            aria-pressed={maximised}
            title={
              maximised
                ? "Back to a windowed editor"
                : "Fill the screen — the panes get the whole width"
            }
            aria-label={maximised ? "Restore the editor" : "Maximise the editor"}
            className="rounded-lg p-1.5 text-ink-subtle transition-colors hover:bg-surface-sunken hover:text-ink-muted"
          >
            {maximised ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
          <button
            onClick={onClose}
            aria-label="Close editor"
            className="rounded-lg p-1 text-ink-subtle transition-colors hover:bg-surface-sunken hover:text-ink-muted"
          >
            <X size={18} />
          </button>
        </div>

        {detail === null ? (
          <div className="flex flex-1 items-center justify-center">
            <Spinner size={22} />
          </div>
        ) : (
          <>
            {proposed && (
              <div className="mx-4 mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs leading-5 text-indigo-800 dark:border-indigo-900 dark:bg-indigo-950/50 dark:text-indigo-200">
                {proposed.note ??
                  "This is the model's re-reading of the page, not the stored content."}{" "}
                Check it against the original beside it — it replaces what is
                stored only when you save.
              </div>
            )}
            <div className="min-h-0 flex-1 overflow-hidden p-4">
              {tab === "summary" ? (
                // one line of routing text — no preview needed
                <Pane label="Summary — used to route questions to this table">
                  <textarea
                    className={srcCls}
                    value={summary}
                    onChange={(e) => setSummary(e.target.value)}
                  />
                </Pane>
              ) : (
                <div
                  className={`grid h-full grid-cols-1 gap-3 ${
                    // written out rather than built from a count, so Tailwind
                    // can see every class it has to keep
                    [
                      "md:grid-cols-2",
                      "md:grid-cols-2 xl:grid-cols-3",
                      "md:grid-cols-2 xl:grid-cols-4",
                    ][(showOriginal ? 1 : 0) + (assistantOpen ? 1 : 0)]
                  }`}
                >
                  {showOriginal && (
                    <Pane
                      label="Original — as printed"
                      action={
                        // on the pane itself, where someone who wants the room
                        // back is already looking
                        <button
                          type="button"
                          onClick={() => setShowOriginal(false)}
                          title="Hide the original and give the width to the source and preview"
                          aria-label="Hide the original"
                          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-ink-subtle transition-colors hover:bg-surface-sunken hover:text-ink"
                        >
                          <X size={12} aria-hidden="true" /> hide
                        </button>
                      }
                    >
                      <div className="h-full overflow-auto rounded-lg border border-line bg-white p-2">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={elementImageUrl(elementId)}
                          alt="The crop of this element as it appears in the document"
                          className="w-full object-contain"
                        />
                      </div>
                    </Pane>
                  )}
                  <Pane
                    label={`Source · ${tab}`}
                    action={
                      tab === "html" && isTable ? (
                        <button
                          type="button"
                          onClick={derive}
                          disabled={deriving || !html.trim()}
                          title="Read the records back out of this HTML and regenerate the routing summary. Correcting the HTML alone leaves answers quoting the old records."
                          className="inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 dark:border-indigo-900 dark:bg-indigo-950/50 dark:text-indigo-300"
                        >
                          {deriving ? <Spinner size={11} /> : <Wand2 size={11} />}
                          rebuild records + summary
                        </button>
                      ) : undefined
                    }
                  >
                    <textarea
                      className={`${srcCls} font-mono text-[12px]`}
                      spellCheck={false}
                      value={
                        tab === "text"
                          ? text
                          : tab === "html"
                            ? html
                            : recordsJson
                      }
                      onChange={(e) =>
                        tab === "text"
                          ? setText(e.target.value)
                          : tab === "html"
                            ? setHtml(e.target.value)
                            : setRecordsJson(e.target.value)
                      }
                    />
                  </Pane>
                  <Pane label="Preview">
                    <div className="h-full overflow-auto rounded-lg border border-line bg-surface p-3 dark:bg-slate-900/40">
                      {tab === "text" && (
                        <div className="chat-md prose prose-sm max-w-none dark:prose-invert">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {text || "_empty_"}
                          </ReactMarkdown>
                        </div>
                      )}
                      {tab === "html" && (
                        <div
                          className="doc-table"
                          dangerouslySetInnerHTML={{ __html: html }}
                        />
                      )}
                      {tab === "records" &&
                        (records.ok ? (
                          <RecordsTable
                            records={
                              records.value as React.ComponentProps<
                                typeof RecordsTable
                              >["records"]
                            }
                          />
                        ) : (
                          <p className="text-xs text-red-600">
                            Invalid JSON: {records.error}
                          </p>
                        ))}
                    </div>
                  </Pane>
                  {assistantOpen && (
                    <EditAssistant
                      elementId={elementId}
                      format={tab}
                      content={
                        tab === "text"
                          ? text
                          : tab === "html"
                            ? html
                            : recordsJson
                      }
                      onApply={(next) =>
                        tab === "text"
                          ? setText(next)
                          : tab === "html"
                            ? setHtml(next)
                            : setRecordsJson(next)
                      }
                    />
                  )}
                </div>
              )}
            </div>

            {/* footer */}
            <div className="flex items-center gap-3 border-t border-line px-4 py-2.5">
              {error ? (
                <p className="text-xs text-red-600">{error}</p>
              ) : (
                derived && (
                  <p className="text-xs text-ink-muted">
                    {derived}
                  </p>
                )
              )}
              <div className="ml-auto flex gap-2">
                <Button variant="secondary" onClick={onClose} disabled={busy}>
                  Cancel
                </Button>
                <Button onClick={save} disabled={busy}>
                  {busy ? "Saving & re-indexing…" : "Save & re-index"}
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
    </Portal>
  );
}

function Pane({
  label,
  children,
  action,
}: {
  label: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-0 flex-col">
      <div className="mb-1 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
        {label}
        {action && <span className="ml-auto normal-case">{action}</span>}
      </div>
      {children}
    </div>
  );
}

const srcCls =
  "min-h-0 flex-1 w-full resize-none rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30";
