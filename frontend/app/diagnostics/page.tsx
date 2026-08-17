"use client";

import { useT } from "@/components/LocaleProvider";
import { useRef, useState } from "react";
import { Eye, FileSearch, Upload } from "lucide-react";
import {
  diagnoseTableDetection,
  type PageDiagnostic,
  type TableDiagnostics,
  type VlmDetection,
} from "@/lib/api";
import { Button, Card, Spinner } from "@/components/ui";

const STRATEGIES = ["lines_strict", "lines", "text"] as const;

export default function DiagnosticsPage() {
  const t = useT();
  const [result, setResult] = useState<TableDiagnostics | null>(null);
  const [busy, setBusy] = useState(false);
  const [vlmBusy, setVlmBusy] = useState<number | null>(null);
  const [vlmResults, setVlmResults] = useState<Record<number, VlmDetection>>({});
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const run = async (file: File) => {
    fileRef.current = file;
    setBusy(true);
    setError(null);
    setResult(null);
    setVlmResults({});
    try {
      setResult(await diagnoseTableDetection(file));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const runVlm = async (page: number) => {
    const file = fileRef.current;
    if (!file || vlmBusy !== null) return;
    setVlmBusy(page);
    setError(null);
    try {
      const res = await diagnoseTableDetection(file, page);
      if (res.vlm) setVlmResults((m) => ({ ...m, [page]: res.vlm! }));
    } catch (e) {
      setError(String(e));
    } finally {
      setVlmBusy(null);
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <FileSearch size={20} className="text-ink-subtle" />
          {t("diag.title")}
        </h1>
        <p className="mt-0.5 max-w-2xl text-sm text-ink-muted">
          {t("diag.lede")}
        </p>
      </div>

      <div
        onClick={() => fileInput.current?.click()}
        className="mb-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-line bg-surface px-6 py-8 text-center hover:border-line-strong"
      >
        <Upload size={24} className="text-ink-faint" />
        <div className="mt-2 text-sm font-medium text-ink">
          {t("diag.choose_pdf")}
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
        <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-muted">
          <Spinner size={18} /> {t("diag.analyzing")}
        </div>
      )}
      {error && (
        <div className="callout callout-danger mb-4">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className="text-sm text-ink-muted">
            <span className="font-medium">{result.filename}</span> ·{" "}
            {result.page_count} page{result.page_count === 1 ? "" : "s"}
          </div>
          {result.pages.map((page, i) => (
            <PageCard
              key={i}
              page={page}
              index={i}
              vlm={vlmResults[i + 1] ?? null}
              vlmBusy={vlmBusy === i + 1}
              onRunVlm={() => runVlm(i + 1)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function PageCard({
  page,
  index,
  vlm,
  vlmBusy,
  onRunVlm,
}: {
  page: PageDiagnostic;
  index: number;
  vlm: VlmDetection | null;
  vlmBusy: boolean;
  onRunVlm: () => void;
}) {
  const t = useT();
  const isScan = page.text_chars < 32;
  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold">Page {index + 1}</h2>
        <span className="text-xs text-ink-subtle">
          {page.width}×{page.height} pt · {page.text_chars} text chars
          {isScan && " · scan (VLM path)"}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {isScan && (
            <Button
              size="sm"
              variant="tonal"
              loading={vlmBusy}
              icon={<Eye size={13} />}
              onClick={onRunVlm}
            >
              {t("diag.vlm_detect")}
            </Button>
          )}
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
              page.kept.length > 0
                ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-800/50"
                : "bg-surface-sunken text-ink-muted"
            }`}
          >
            {page.kept.length} kept (text-layer)
          </span>
        </div>
      </div>

      {!isScan && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-ink-subtle">
                <th className="py-1.5 pr-3 font-medium">{t("diag.col_strategy")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("diag.col_found")}</th>
                <th className="py-1.5 font-medium">
                  {t("diag.col_tables")}
                </th>
              </tr>
            </thead>
            <tbody>
              {STRATEGIES.map((s) => {
                const info = page.strategies[s];
                return (
                  <tr key={s} className="border-t border-line align-top">
                    <td className="py-1.5 pr-3 font-mono text-ink-muted">{s}</td>
                    <td className="py-1.5 pr-3 text-ink-muted">
                      {info?.error ? "error" : (info?.count ?? 0)}
                    </td>
                    <td className="py-1.5">
                      {info?.error ? (
                        <span className="text-red-600">{info.error}</span>
                      ) : info?.tables && info.tables.length > 0 ? (
                        <div className="space-y-0.5">
                          {info.tables.map((t, j) => (
                            <div key={j} className="font-mono text-ink-muted">
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
                        <span className="text-ink-subtle">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {vlm && (
        <div className="mt-3 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3 text-xs">
          <div className="mb-1 font-medium text-indigo-700">
            VLM region detection: {vlm.count} table
            {vlm.count === 1 ? "" : "s"}
          </div>
          {vlm.boxes.length > 0 && (
            <div className="mb-2 space-y-0.5 font-mono text-ink-muted">
              {vlm.boxes.map((b, j) => (
                <div key={j}>
                  box {j + 1}: x {Math.round(b[0] * 100)}–{Math.round(b[2] * 100)}
                  % · y {Math.round(b[1] * 100)}–{Math.round(b[3] * 100)}%
                </div>
              ))}
            </div>
          )}
          <details>
            <summary className="cursor-pointer text-ink-muted">
              {t("diag.raw_reply")}
            </summary>
            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-surface p-2 text-[11px] text-ink-muted">
              {vlm.raw}
            </pre>
          </details>
        </div>
      )}
    </Card>
  );
}
