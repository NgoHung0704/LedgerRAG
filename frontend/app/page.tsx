"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Database, FolderPlus, Globe, Plus } from "lucide-react";
import { createKb, getKbs, type KB } from "@/lib/api";
import { Button, Card, EmptyState, Modal, Spinner, inputCls } from "@/components/ui";

const LOCALES = [
  { value: "", label: "Not specified" },
  { value: "fr", label: "Français (1 234,56)" },
  { value: "de", label: "Deutsch (1.234,56)" },
  { value: "en", label: "English (1,234.56)" },
  { value: "es", label: "Español (1.234,56)" },
  { value: "it", label: "Italiano (1.234,56)" },
  { value: "pt", label: "Português (1.234,56)" },
];

export default function HomePage() {
  const [kbs, setKbs] = useState<KB[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const refresh = () =>
    getKbs()
      .then(setKbs)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Knowledge Bases</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Each knowledge base is an isolated corpus with its own documents.
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus size={16} /> New knowledge base
        </Button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          {error}
        </div>
      )}

      {kbs === null ? (
        <div className="flex justify-center py-16">
          <Spinner size={22} />
        </div>
      ) : kbs.length === 0 ? (
        <EmptyState
          icon={<FolderPlus size={36} />}
          title="No knowledge bases yet"
          hint="Create one, then drop your PDF documents on it — policies, reports, anything with tables."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {kbs.map((kb) => (
            <Link key={kb.id} href={`/kb/${kb.id}`}>
              <Card className="group h-full p-4 transition-shadow hover:shadow-md">
                <div className="mb-3 flex items-start justify-between">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                    <Database size={18} />
                  </div>
                  {kb.config?.locale && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium uppercase text-slate-500">
                      <Globe size={11} /> {kb.config.locale}
                    </span>
                  )}
                </div>
                <div className="font-medium text-slate-900 group-hover:text-indigo-700">
                  {kb.name}
                </div>
                <p className="mt-1 line-clamp-2 min-h-[2rem] text-[13px] leading-5 text-slate-500">
                  {kb.description || "No description — add one, the router will use it."}
                </p>
                <div className="mt-3 text-[11px] text-slate-400">
                  {new Date(kb.created_at).toLocaleDateString()}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}

function CreateModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [locale, setLocale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createKb(name.trim(), description.trim(), locale || null);
      onCreated();
    } catch (err) {
      setError(String(err));
      setBusy(false);
    }
  };

  return (
    <Modal title="New knowledge base" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">
            Name
          </label>
          <input
            className={inputCls}
            placeholder="e.g. HR policies"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">
            Description
          </label>
          <textarea
            className={`${inputCls} resize-none`}
            rows={3}
            placeholder="What documents live here? Used later to route questions to the right knowledge base."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">
            Number locale of the documents
          </label>
          <select
            className={inputCls}
            value={locale}
            onChange={(e) => setLocale(e.target.value)}
          >
            {LOCALES.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[11px] leading-4 text-slate-400">
            How numbers are printed in your documents. Declaring it avoids
            guessing when normalizing table values.
          </p>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy || !name.trim()}>
            {busy ? "Creating…" : "Create"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
