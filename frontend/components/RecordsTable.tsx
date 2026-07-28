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
    <div className="max-h-72 overflow-auto rounded-lg border border-slate-200 dark:border-slate-700">
      <table className="w-full text-[12px]">
        <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
          <tr>
            {dimKeys.map((k) => (
              <th
                key={k}
                className="border-b border-slate-200 px-2.5 py-1.5 text-left font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400"
              >
                {k}
              </th>
            ))}
            {metricKeys.map((k) => (
              <th
                key={k}
                className="border-b border-slate-200 px-2.5 py-1.5 text-right font-semibold text-indigo-600 dark:border-slate-700 dark:text-indigo-300"
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
              className="odd:bg-white even:bg-slate-50/50 dark:odd:bg-transparent dark:even:bg-slate-800/40"
            >
              {dimKeys.map((k) => (
                <td
                  key={k}
                  className="px-2.5 py-1 text-slate-700 dark:text-slate-300"
                >
                  {String(r.dimensions[k] ?? "")}
                </td>
              ))}
              {metricKeys.map((k) => (
                <td
                  key={k}
                  className="px-2.5 py-1 text-right tabular-nums text-slate-800 dark:text-slate-200"
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
