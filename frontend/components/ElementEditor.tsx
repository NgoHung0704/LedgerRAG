"use client";

import { useEffect, useState } from "react";
import {
  editElement,
  getElement,
  type ElementDetail,
  type ElementEdit,
} from "@/lib/api";
import { Button, Modal, Spinner } from "@/components/ui";

/** Manual correction of a parsed element. Loads the full element (text /
 * html / summary / records), lets an admin fix anything, and on save the
 * backend re-indexes so answers use the corrected data. */
export default function ElementEditor({
  elementId,
  onClose,
  onSaved,
}: {
  elementId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [detail, setDetail] = useState<ElementDetail | null>(null);
  const [text, setText] = useState("");
  const [html, setHtml] = useState("");
  const [summary, setSummary] = useState("");
  const [recordsJson, setRecordsJson] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getElement(elementId)
      .then((d) => {
        setDetail(d);
        setText(d.text ?? "");
        setHtml(d.table?.html ?? "");
        setSummary(d.table?.summary ?? "");
        setRecordsJson(
          d.table ? JSON.stringify(d.table.records, null, 2) : "",
        );
      })
      .catch((e) => setError(String(e)));
  }, [elementId]);

  const save = async () => {
    setError(null);
    const edit: ElementEdit = {};
    if (detail?.type === "text") edit.text = text;
    if (detail?.table) {
      edit.html = html;
      edit.summary = summary;
      try {
        const parsed = JSON.parse(recordsJson);
        if (!Array.isArray(parsed)) throw new Error("records must be an array");
        edit.records = parsed;
      } catch (e) {
        setError(`Records JSON is invalid: ${e instanceof Error ? e.message : e}`);
        return;
      }
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
    <Modal title="Edit parsed element" onClose={onClose} wide>
      {detail === null ? (
        <div className="flex justify-center py-10">
          <Spinner size={20} />
        </div>
      ) : (
        <div className="space-y-4">
          <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
            Correct anything below. On save, this element is re-indexed so
            future answers use your corrections.
          </p>

          {detail.type === "text" && (
            <Field label="Extracted text (re-chunked & re-embedded on save)">
              <textarea
                className={taCls}
                rows={12}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </Field>
          )}

          {detail.table && (
            <>
              <Field label="HTML — display, and what answers quote for tables">
                <textarea
                  className={`${taCls} font-mono text-[12px]`}
                  rows={10}
                  value={html}
                  onChange={(e) => setHtml(e.target.value)}
                />
              </Field>
              <Field label="Summary — used to route questions to this table">
                <textarea
                  className={taCls}
                  rows={2}
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                />
              </Field>
              <Field label="Records (JSON) — dimensions/metrics/raw_values answers look up">
                <textarea
                  className={`${taCls} font-mono text-[11px]`}
                  rows={12}
                  value={recordsJson}
                  onChange={(e) => setRecordsJson(e.target.value)}
                />
              </Field>
            </>
          )}

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={save} disabled={busy}>
              {busy ? "Saving & re-indexing…" : "Save & re-index"}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-slate-400">
        {label}
      </label>
      {children}
    </div>
  );
}

const taCls =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100";
