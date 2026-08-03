"use client";

// A parsed table's records (dimensions + metrics + raw_values) as a grid.
// Shared by the Document Inspector and the element editor's live preview, so it
// accepts a loose record shape (RecordPreview from the view, RecordEdit from a
// full element) — it only reads and string-coerces the values.
type LooseRecord = {
  dimensions: Record<string, unknown>;
  metrics: Record<string, unknown>;
  raw_values: Record<string, unknown>;
};

export default function RecordsTable({ records }: { records: LooseRecord[] }) {
  if (records.length === 0) return null;
  const dimKeys = Object.keys(records[0].dimensions);
  const metricKeys = Object.keys(records[0].metrics);
  return (
    <div className="max-h-72 overflow-auto rounded-lg border border-line">
      <table className="w-full text-[12px]">
        <thead className="sticky top-0 bg-surface-sunken">
          <tr>
            {dimKeys.map((k) => (
              <th
                key={k}
                className="border-b border-line px-2.5 py-1.5 text-left font-semibold text-ink-muted"
              >
                {k}
              </th>
            ))}
            {metricKeys.map((k) => (
              <th
                key={k}
                className="border-b border-line px-2.5 py-1.5 text-right font-semibold text-indigo-600 dark:text-indigo-300"
              >
                {k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {records.map((r, i) => (
            <tr
              key={i}
              className="odd:bg-surface even:bg-slate-50/50 dark:odd:bg-transparent dark:even:bg-slate-800/40"
            >
              {dimKeys.map((k) => (
                <td
                  key={k}
                  className="px-2.5 py-1 text-ink"
                >
                  {String(r.dimensions[k] ?? "")}
                </td>
              ))}
              {metricKeys.map((k) => (
                <td
                  key={k}
                  className="px-2.5 py-1 text-right tabular-nums text-ink"
                  title={`normalized: ${String(r.metrics[k] ?? "null")}`}
                >
                  {String(r.raw_values[k] ?? r.metrics[k] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
