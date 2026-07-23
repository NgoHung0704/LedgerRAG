"use client";

import { useState } from "react";
import { Pencil, Sparkles, Check, X } from "lucide-react";
import { suggestDescription, updateKb, type KB } from "@/lib/api";
import { Spinner } from "@/components/ui";

// The description is what the router reads to decide when to search a KB
// (SPEC Phase 5), so it is editable here with a one-click draft from the
// KB's own documents — a weak description blinds the router.
export default function KbDescription({
  kb,
  onUpdated,
}: {
  kb: KB;
  onUpdated: (kb: KB) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(kb.description ?? "");
  const [saving, setSaving] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = () => {
    setText(kb.description ?? "");
    setError(null);
    setEditing(true);
  };

  const suggest = async () => {
    setSuggesting(true);
    setError(null);
    try {
      const { description } = await suggestDescription(kb.id);
      setText(description);
    } catch {
      setError(
        "Couldn't draft a description — upload a document and let it finish first.",
      );
    } finally {
      setSuggesting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateKb(kb.id, { description: text.trim() });
      onUpdated(updated);
      setEditing(false);
    } catch {
      setError("Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <div className="group mt-1 flex max-w-2xl items-start gap-2">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {kb.description || (
            <span className="italic text-slate-400">
              No description yet — add one so it can be auto-routed.
            </span>
          )}
        </p>
        <button
          onClick={start}
          title="Edit description"
          className="mt-0.5 shrink-0 text-slate-300 opacity-0 transition-opacity hover:text-indigo-600 group-hover:opacity-100"
        >
          <Pencil size={13} />
        </button>
      </div>
    );
  }

  return (
    <div className="mt-2 max-w-2xl">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder="What subjects does this knowledge base cover?"
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:ring-indigo-900/40"
      />
      {error && <div className="mt-1 text-xs text-red-600">{error}</div>}
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={suggest}
          disabled={suggesting || saving}
          className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-1.5 text-[12px] font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 dark:border-indigo-900 dark:bg-indigo-950/50 dark:text-indigo-300 dark:hover:bg-indigo-950"
        >
          {suggesting ? <Spinner size={13} /> : <Sparkles size={13} />}
          Suggest from documents
        </button>
        <div className="ml-auto flex gap-1.5">
          <button
            onClick={() => setEditing(false)}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            <X size={13} /> Cancel
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-indigo-500 disabled:bg-indigo-300"
          >
            {saving ? <Spinner size={13} /> : <Check size={13} />} Save
          </button>
        </div>
      </div>
    </div>
  );
}
