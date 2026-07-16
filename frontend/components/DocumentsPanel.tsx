"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertCircle, FileUp, Files, ScanSearch, Trash2 } from "lucide-react";
import { bulkDeleteDocs, deleteDoc, getDocs, uploadDoc, type Doc } from "@/lib/api";
import { Button, Card, EmptyState, Spinner, StatusPill } from "@/components/ui";

export default function DocumentsPanel({ kbId }: { kbId: string }) {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(
    () => getDocs(kbId).then(setDocs).catch(() => {}),
    [kbId],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  // poll while any document is still being processed
  const processing = (docs ?? []).some(
    (d) => !["done", "failed"].includes(d.status),
  );
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [processing, refresh]);

  const handleFiles = async (files: FileList | File[] | null) => {
    if (!files) return;
    setUploadError(null);
    for (const file of Array.from(files)) {
      try {
        await uploadDoc(kbId, file);
      } catch (e) {
        setUploadError(`${file.name}: ${e instanceof Error ? e.message : e}`);
      }
    }
    refresh();
  };

  const remove = async (d: Doc) => {
    if (!window.confirm(`Delete "${d.filename}" and all its parsed data? This cannot be undone.`))
      return;
    setDeleting(d.id);
    try {
      await deleteDoc(d.id);
      setSelected((s) => {
        const next = new Set(s);
        next.delete(d.id);
        return next;
      });
      await refresh();
    } catch (e) {
      setUploadError(String(e));
    } finally {
      setDeleting(null);
    }
  };

  const allDocs = docs ?? [];
  const allSelected = allDocs.length > 0 && selected.size === allDocs.length;
  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(allDocs.map((d) => d.id)));

  const removeSelected = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(
      `Delete ${selected.size} document${selected.size === 1 ? "" : "s"} and all their parsed data? This cannot be undone.`,
    ))
      return;
    setBulkBusy(true);
    setUploadError(null);
    try {
      await bulkDeleteDocs(kbId, Array.from(selected));
      setSelected(new Set());
      await refresh();
    } catch (e) {
      setUploadError(String(e));
    } finally {
      setBulkBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInput.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors ${
          dragOver
            ? "border-indigo-400 bg-indigo-50"
            : "border-slate-200 bg-white hover:border-slate-300"
        }`}
      >
        <FileUp
          size={26}
          className={dragOver ? "text-indigo-500" : "text-slate-300"}
        />
        <div className="mt-2 text-sm font-medium text-slate-700">
          Drop PDF documents here, or click to browse
        </div>
        <div className="mt-0.5 text-xs text-slate-400">
          Tables keep their original image — parsing is verified, never guessed.
        </div>
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf"
          multiple
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {uploadError && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          {uploadError}
        </div>
      )}

      {docs !== null && docs.length === 0 ? (
        <EmptyState
          icon={<Files size={34} />}
          title="No documents yet"
          hint="Upload PDFs above. Ingestion runs in the background — status updates live."
        />
      ) : (
        <Card className="overflow-hidden">
          {selected.size > 0 && (
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 bg-indigo-50/50 px-4 py-2">
              <span className="text-sm text-slate-600">
                {selected.size} selected
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelected(new Set())}
                  className="text-xs text-slate-500 hover:text-slate-700"
                >
                  Clear
                </button>
                <Button
                  variant="secondary"
                  className="!py-1.5 text-xs !text-red-600"
                  disabled={bulkBusy}
                  onClick={removeSelected}
                >
                  {bulkBusy ? <Spinner size={13} /> : <Trash2 size={13} />}
                  Delete selected
                </Button>
              </div>
            </div>
          )}
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs font-medium uppercase tracking-wide text-slate-400">
                <th className="w-10 px-4 py-2.5">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                    title="Select all"
                  />
                </th>
                <th className="px-4 py-2.5">Document</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Pages</th>
                <th className="px-4 py-2.5">Added</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {(docs ?? []).map((d) => (
                <tr
                  key={d.id}
                  className={`border-b border-slate-50 last:border-0 hover:bg-slate-50/50 ${
                    selected.has(d.id) ? "bg-indigo-50/40" : ""
                  }`}
                >
                  <td className="px-4 py-2.5">
                    <input
                      type="checkbox"
                      checked={selected.has(d.id)}
                      onChange={() => toggle(d.id)}
                      className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                    />
                  </td>
                  <td className="max-w-[22rem] px-4 py-2.5">
                    <Link
                      href={`/doc/${d.id}`}
                      className="block truncate font-medium text-slate-800 hover:text-indigo-700"
                      title="Inspect parsed output"
                    >
                      {d.filename}
                    </Link>
                    {d.status === "failed" && d.error && (
                      <div className="mt-0.5 text-xs text-red-600">{d.error}</div>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusPill status={d.status} />
                  </td>
                  <td className="px-4 py-2.5 text-slate-500">
                    {d.page_count ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-slate-500">
                    {new Date(d.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center justify-end gap-1">
                      <Link
                        href={`/doc/${d.id}`}
                        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
                      >
                        <ScanSearch size={13} /> Inspect
                      </Link>
                      <button
                        onClick={() => remove(d)}
                        disabled={deleting === d.id}
                        title="Delete document"
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                      >
                        {deleting === d.id ? <Spinner size={13} /> : <Trash2 size={13} />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
