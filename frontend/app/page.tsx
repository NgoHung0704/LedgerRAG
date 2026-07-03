"use client";

import { useEffect, useState } from "react";
import { createKb, getKbs, type KB } from "@/lib/api";

export default function HomePage() {
  const [kbs, setKbs] = useState<KB[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = () =>
    getKbs()
      .then(setKbs)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));

  useEffect(() => {
    refresh();
  }, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    try {
      await createKb(name.trim(), description.trim());
      setName("");
      setDescription("");
      refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-3 font-semibold">New knowledge base</h2>
        <form onSubmit={onCreate} className="flex flex-col gap-2 sm:flex-row">
          <input
            className="flex-1 rounded border px-3 py-2 text-sm"
            placeholder="Name (e.g. HR policies)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="flex-[2] rounded border px-3 py-2 text-sm"
            placeholder="Description — what documents live here (used for routing later)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <button
            type="submit"
            className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
          >
            Create
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </section>

      <section>
        <h2 className="mb-3 font-semibold">Knowledge bases</h2>
        {loading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : kbs.length === 0 ? (
          <p className="text-sm text-slate-500">
            No knowledge bases yet — create one above, then upload PDFs.
          </p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {kbs.map((kb) => (
              <li key={kb.id}>
                <a
                  href={`/kb/${kb.id}`}
                  className="block rounded-lg border bg-white p-4 hover:border-slate-400"
                >
                  <div className="font-medium">{kb.name}</div>
                  <div className="mt-1 line-clamp-2 text-sm text-slate-500">
                    {kb.description || "No description"}
                  </div>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
