"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ChevronRight, CheckCircle2, Table2, FileText } from "lucide-react";
import { getNeedsReview, type ReviewItem } from "@/lib/api";
import { Spinner } from "@/components/ui";

// SPEC Phase 5: pull needs_review out of per-document admin into a natural
// flow. Each item links to the document viewer, where the parse can be checked
// against the original crop and approved or marked unusable.
export default function ReviewPanel({
  kbId,
  onCount,
}: {
  kbId: string;
  onCount?: (n: number) => void;
}) {
  const [items, setItems] = useState<ReviewItem[] | null>(null);

  useEffect(() => {
    getNeedsReview(kbId)
      .then((r) => {
        setItems(r.items);
        onCount?.(r.count);
      })
      .catch(() => setItems([]));
  }, [kbId, onCount]);

  if (items === null)
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-ink-subtle">
        <Spinner size={15} /> Loading…
      </div>
    );

  if (items.length === 0)
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-line bg-surface p-10 text-center shadow-card">
        <CheckCircle2 size={26} className="mb-2 text-emerald-500" />
        <div className="text-sm font-medium text-ink-muted">
          Nothing to review
        </div>
        <div className="mt-1 max-w-sm text-xs text-ink-subtle">
          Every table was read with confidence. Flagged tables show up here so
          you can check them against the original before trusting a number.
        </div>
      </div>
    );

  return (
    <div className="rounded-xl border border-line bg-surface shadow-card">
      <div className="flex items-center gap-2 border-b border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
        <AlertTriangle size={15} />
        <span className="font-medium">
          {items.length} table{items.length === 1 ? "" : "s"} to check
        </span>
        <span className="text-amber-600 dark:text-amber-400/80">
          — the parser wasn't sure. Open each to compare with the original and
          approve, edit, or set it aside.
        </span>
      </div>
      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {items.map((it) => (
          <li key={it.element_id}>
            <Link
              href={`/doc/${it.doc_id}#el-${it.element_id}`}
              className="flex items-center gap-3 px-4 py-3 hover:bg-surface-sunken dark:hover:bg-slate-800/60"
            >
              <span className="text-amber-500">
                {it.type === "table" ? <Table2 size={16} /> : <FileText size={16} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-ink">
                  {it.filename}
                </span>
                <span className="text-xs text-ink-subtle">
                  page {it.page}
                  {it.confidence != null &&
                    ` · confidence ${Math.round(it.confidence * 100)}%`}
                </span>
              </span>
              <ChevronRight size={16} className="text-ink-faint" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
