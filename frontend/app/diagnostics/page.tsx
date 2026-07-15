"use client";

import { useRef, useState } from "react";
import { FileSearch, Upload } from "lucide-react";
import {
  diagnoseTableDetection,
  type PageDiagnostic,
  type TableDiagnostics,
} from "@/lib/api";
import { Button, Card, Spinner } from "@/components/ui";

const STRATEGIES = ["lines_strict", "lines", "text"] as const;

export default function DiagnosticsPage() {
  const [result, setResult] = useState<TableDiagnostics | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const run = async (file: File) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await diagnoseTableDetection(file));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <FileSearch size={20} className="text-slate-400" />
          Table detection diagnostics
        </h1>
        <p className="mt-0.5 max-w-2xl text-sm text-slate-500">
          Upload a PDF to see how many tables each detection strategy finds on
          each page, and which regions ingestion would keep. Nothing is stored —
          the file is analyzed and discarded. Use this to debug a real-document
          table that shows up as text instead of a table.
        </p>
      </div>

      <div
        onClick={() => fileInput.current?.click()}
        className="mb-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-white px-6 py-8 text-center hover:border-slate-300"
      >
        <Upload size={24} className="text-slate-300" />
        <div className="mt-2 text-sm font-medium text-slate-700">
          Click to choose a PDF
        </div>
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) run(f);
            e.target.value = "";
          }}
        />
      </div>

      {busy && (
        <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
          <Spinner size={18} /> analyzing…
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className="text-sm text-slate-600">
            <span className="font-medium">{result.filename}</span> ·{" "}
            {result.page_count} page{result.page_count === 1 ? "" : "s"}
          </div>
          {result.pages.map((page, i) => (
            <PageCard key={i} page={page} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

function PageCard({ page, index }: { page: PageDiagnostic; index: number }) {
  const isScan = page.text_chars < 32;
  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold">Page {index + 1}</h2>
        <span className="text-xs text-slate-400">
          {page.width}×{page.height} pt · {page.text_chars} text chars
          {isScan && " · looks like a scan (VLM path)"}
        </span>
        <span
          className={`ml-auto rounded-full px-2.5 py-0.5 text-xs font-medium ${
            page.kept.length > 0
              ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
              : "bg-slate-100 text-slate-500"
          }`}
        >
          {page.kept.length} table{page.kept.length === 1 ? "" : "s"} kept
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-slate-400">
              <th className="py-1.5 pr-3 font-medium">strategy</th>
              <th className="py-1.5 pr-3 font-medium">found</th>
              <th className="py-1.5 font-medium">tables (bbox · rows×cols · fill · accept)</th>
            </tr>
          </thead>
          <tbody>
            {STRATEGIES.map((s) => {
              const info = page.strategies[s];
              return (
                <tr key={s} className="border-t border-slate-100 align-top">
                  <td className="py-1.5 pr-3 font-mono text-slate-600">{s}</td>
                  <td className="py-1.5 pr-3 text-slate-600">
                    {info?.error ? "error" : (info?.count ?? 0)}
                  </td>
                  <td className="py-1.5">
                    {info?.error ? (
                      <span className="text-red-600">{info.error}</span>
                    ) : info?.tables && info.tables.length > 0 ? (
                      <div className="space-y-0.5">
                        {info.tables.map((t, j) => (
                          <div key={j} className="font-mono text-slate-600">
                            [{t.bbox.map((n) => Math.round(n)).join(",")}] ·{" "}
                            {t.rows}×{t.cols} · fill {t.fill} ·{" "}
                            <span
                              className={
                                t.accept ? "text-emerald-600" : "text-red-600"
                              }
                            >
                              accept {t.accept ? "yes" : "no"}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {page.kept.length > 0 && (
        <div className="mt-3 border-t border-slate-100 pt-2 text-xs text-slate-500">
          kept:{" "}
          {page.kept.map((t, j) => (
            <span key={j} className="mr-2 font-mono">
              [{t.bbox.map((n) => Math.round(n)).join(",")}] {t.rows}×{t.cols}
              {t.complex ? " (vlm)" : " (simple)"}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}
