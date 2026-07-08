"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, FileUp, Files } from "lucide-react";
import { getDocs, uploadDoc, type Doc } from "@/lib/api";
import { Card, EmptyState, StatusPill } from "@/components/ui";

export default function DocumentsPanel({ kbId }: { kbId: string }) {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
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
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs font-medium uppercase tracking-wide text-slate-400">
                <th className="px-4 py-2.5">Document</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Pages</th>
                <th className="px-4 py-2.5">Added</th>
              </tr>
            </thead>
            <tbody>
              {(docs ?? []).map((d) => (
                <tr
                  key={d.id}
                  className="border-b border-slate-50 last:border-0 hover:bg-slate-50/50"
                >
                  <td className="max-w-[22rem] px-4 py-2.5">
                    <div className="truncate font-medium text-slate-800">
                      {d.filename}
                    </div>
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
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
