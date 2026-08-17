"use client";

import { useT } from "@/components/LocaleProvider";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  FileUp,
  Files,
  RefreshCw,
  ScanSearch,
  Trash2,
} from "lucide-react";
import {
  bulkDeleteDocs,
  bulkReprocessDocs,
  deleteDoc,
  getDocs,
  reprocessDoc,
  uploadDoc,
  type Doc,
} from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  IconButton,
  Spinner,
  StatusPill,
} from "@/components/ui";
import { confirm } from "@/components/confirm";

const plural = (n: number) => (n === 1 ? "" : "s");

export default function DocumentsPanel({ kbId }: { kbId: string }) {
  const t = useT();
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [reprocessing, setReprocessing] = useState<string | null>(null);
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

  const reprocess = async (d: Doc) => {
    // a failed document has nothing to lose; a successful one does — every
    // element is replaced, and corrections made to them go with it
    if (
      d.status !== "failed" &&
      !(await confirm({
        title: t("doc.reprocess_confirm", { filename: d.filename }),
        message: t("doc.reprocess_body"),
        confirmLabel: t("doc.reprocess"),
        danger: false,
      }))
    )
      return;
    setReprocessing(d.id);
    setUploadError(null);
    try {
      await reprocessDoc(d.id);
      await refresh(); // status flips to queued; the poll below tracks it
    } catch (e) {
      setUploadError(String(e));
    } finally {
      setReprocessing(null);
    }
  };

  const remove = async (d: Doc) => {
    if (
      !(await confirm({
        title: t("doc.delete_confirm", { filename: d.filename }),
        message: t("doc.delete_body"),
        confirmLabel: t("common.delete"),
      }))
    )
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

  const reprocessSelected = async () => {
    if (selected.size === 0) return;
    if (
      !(await confirm({
        title: `Reprocess ${selected.size} document${plural(selected.size)}?`,
        message:
          `Parsed elements are rebuilt from the original files, so any manual ` +
          `corrections on them are replaced. The worker takes documents one at ` +
          `a time — a large batch will take a while.`,
        confirmLabel: t("doc.reprocess"),
        danger: false,
      }))
    )
      return;
    setBulkBusy(true);
    setUploadError(null);
    try {
      const { queued, skipped } = await bulkReprocessDocs(
        kbId,
        Array.from(selected),
      );
      if (skipped > 0)
        setUploadError(
          `${queued} queued · ${skipped} skipped (already being processed).`,
        );
      setSelected(new Set());
      await refresh();
    } catch (e) {
      setUploadError(String(e));
    } finally {
      setBulkBusy(false);
    }
  };

  const removeSelected = async () => {
    if (selected.size === 0) return;
    if (
      !(await confirm({
        title: `Delete ${selected.size} document${plural(selected.size)}?`,
        message: t("doc.delete_many_body"),
        confirmLabel: `Delete ${selected.size} document${plural(selected.size)}`,
      }))
    )
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
            ? "border-indigo-400 bg-indigo-50 dark:bg-indigo-950/40"
            : "border-line bg-surface hover:border-line-strong"
        }`}
      >
        <FileUp
          size={26}
          className={dragOver ? "text-indigo-500" : "text-ink-faint"}
        />
        <div className="mt-2 text-sm font-medium text-ink">
          {t("doc.drop_here")}
        </div>
        <div className="mt-0.5 text-xs text-ink-subtle">
          {t("doc.formats")}
        </div>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.pptx,.ppt,.docx,.doc,.xlsx,.xls"
          multiple
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {uploadError && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          {uploadError}
        </div>
      )}

      {docs !== null && docs.length === 0 ? (
        <EmptyState
          icon={<Files size={34} />}
          title={t("doc.none_yet")}
          hint={t("doc.none_yet_hint")}
        />
      ) : (
        <Card className="overflow-hidden">
          {selected.size > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line bg-indigo-50/50 px-4 py-2 dark:bg-indigo-950/30">
              <span className="text-sm text-ink-muted">
                {selected.size} selected
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
                  {t("doc.clear")}
                </Button>
                <Button
                  variant="tonal"
                  size="sm"
                  loading={bulkBusy}
                  icon={<RefreshCw size={13} />}
                  onClick={reprocessSelected}
                  title={t("doc.reprocess_hint")}
                >
                  {t("doc.reprocess")}
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={bulkBusy}
                  onClick={removeSelected}
                >
                  {bulkBusy ? <Spinner size={13} /> : <Trash2 size={13} />}
                  Delete
                </Button>
              </div>
            </div>
          )}
          {/* the table scrolls inside its own card rather than pushing the
              whole page sideways; Pages and Added drop out first on narrow
              screens, since neither is why you came to this list */}
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs font-medium uppercase tracking-wide text-ink-subtle">
                <th className="w-10 px-4 py-2.5">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    className="h-4 w-4 rounded border-line-strong text-indigo-600"
                    aria-label={allSelected ? t("doc.clear_selection") : t("doc.select_all")}
                  />
                </th>
                <th className="px-4 py-2.5">{t("doc.col_document")}</th>
                <th className="px-4 py-2.5">{t("doc.col_status")}</th>
                <th className="hidden px-4 py-2.5 sm:table-cell">{t("doc.col_pages")}</th>
                <th className="hidden px-4 py-2.5 md:table-cell">{t("doc.col_added")}</th>
                <th className="px-4 py-2.5">
                  <span className="sr-only">{t("doc.col_actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {(docs ?? []).map((d) => (
                <tr
                  key={d.id}
                  className={`border-b border-line last:border-0 hover:bg-surface-sunken ${
                    selected.has(d.id) ? "bg-indigo-50/40 dark:bg-indigo-950/30" : ""
                  }`}
                >
                  <td className="px-4 py-2.5">
                    <input
                      type="checkbox"
                      checked={selected.has(d.id)}
                      onChange={() => toggle(d.id)}
                      aria-label={`Select ${d.filename}`}
                      className="h-4 w-4 rounded border-line-strong text-indigo-600"
                    />
                  </td>
                  <td className="max-w-[22rem] px-4 py-2.5">
                    <Link
                      href={`/doc/${d.id}`}
                      className="block truncate font-medium text-ink hover:text-indigo-700 dark:hover:text-indigo-300"
                      title={t("doc.inspect_hint")}
                    >
                      {d.filename}
                    </Link>
                    {d.status === "failed" && d.error && (
                      <div className="mt-0.5 text-xs text-red-600 dark:text-red-400">{d.error}</div>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusPill status={d.status} />
                  </td>
                  <td className="hidden px-4 py-2.5 text-ink-muted sm:table-cell">
                    {d.page_count ?? "—"}
                  </td>
                  <td className="hidden px-4 py-2.5 text-ink-muted md:table-cell">
                    {new Date(d.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center justify-end gap-1">
                      {/* not only after a failure: parsing improves, and a
                          document that succeeded under an older version is
                          exactly the one that needs running again */}
                      {!["queued", "parsing", "indexing"].includes(d.status) && (
                        <button
                          onClick={() => reprocess(d)}
                          disabled={reprocessing === d.id}
                          title={
                            d.status === "failed"
                              ? "Clear the error and run ingestion again"
                              : "Run ingestion again — picks up parsing changes. The current elements are replaced, and any manual corrections to them are lost."
                          }
                          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 disabled:opacity-50 dark:text-indigo-300 dark:hover:bg-indigo-950/50"
                        >
                          {reprocessing === d.id ? (
                            <Spinner size={13} />
                          ) : (
                            <RefreshCw size={13} />
                          )}
                          {t("doc.reprocess")}
                        </button>
                      )}
                      <Link
                        href={`/doc/${d.id}`}
                        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 dark:text-indigo-300 dark:hover:bg-indigo-950/50"
                      >
                        <ScanSearch size={13} /> {t("doc.inspect")}
                      </Link>
                      <IconButton
                        label={`Delete ${d.filename}`}
                        onClick={() => remove(d)}
                        disabled={deleting === d.id}
                        className="hover:!bg-red-50 hover:!text-red-600 dark:hover:!bg-red-950/40 dark:hover:!text-red-400"
                      >
                        {deleting === d.id ? <Spinner size={13} /> : <Trash2 size={13} />}
                      </IconButton>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Card>
      )}
    </div>
  );
}
