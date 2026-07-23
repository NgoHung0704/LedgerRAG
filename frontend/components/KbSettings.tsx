"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Settings2, Trash2, Check, ShieldCheck, Sparkles } from "lucide-react";
import { updateKb, deleteKb, suggestDescription, type KB } from "@/lib/api";
import { Spinner } from "@/components/ui";

// The single place to edit a KB after creation: name, description (what the
// router reads to pick this KB — SPEC Phase 5), number locale, verification,
// and delete. `defaultOpen` lets the list's ⋮ menu land here with it already
// open, so "Settings & rename" doesn't need a second click.
export default function KbSettings({
  kb,
  onUpdated,
  defaultOpen = false,
}: {
  kb: KB;
  onUpdated: (kb: KB) => void;
  defaultOpen?: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(defaultOpen);
  const ref = useRef<HTMLDivElement>(null);

  const [name, setName] = useState(kb.name);
  const [description, setDescription] = useState(kb.description ?? "");
  const [instructions, setInstructions] = useState(kb.config?.instructions ?? "");
  const [locale, setLocale] = useState(kb.config?.locale ?? "");
  const [verify, setVerify] = useState(kb.config?.verify ?? true);
  const [saving, setSaving] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // open when asked to (list ⋮ → ?settings=1), whether that arrives at mount
  // or a tick later once the KB has loaded
  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setConfirming(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const dirty =
    name.trim() !== kb.name ||
    description.trim() !== (kb.description ?? "") ||
    instructions.trim() !== (kb.config?.instructions ?? "") ||
    (locale || "") !== (kb.config?.locale ?? "") ||
    verify !== (kb.config?.verify ?? true);

  const suggest = async () => {
    setSuggesting(true);
    setError(null);
    try {
      const res = await suggestDescription(kb.id);
      setDescription(res.description);
    } catch {
      setError("Couldn't draft — upload a document and let it finish first.");
    } finally {
      setSuggesting(false);
    }
  };

  const save = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateKb(kb.id, {
        name: name.trim(),
        description: description.trim(),
        instructions: instructions.trim(),
        locale: locale.trim(),
        verify,
      });
      onUpdated(updated);
      setOpen(false);
    } catch {
      setError("Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    setDeleting(true);
    try {
      await deleteKb(kb.id);
      router.push("/");
    } catch {
      setDeleting(false);
      setConfirming(false);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        title="Knowledge base settings"
        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-slate-600 hover:border-indigo-300 hover:text-indigo-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-indigo-500"
      >
        <Settings2 size={14} /> Settings
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-1.5 w-96 max-w-[90vw] rounded-xl border border-slate-200 bg-white p-3.5 shadow-lg dark:border-slate-700 dark:bg-[#1b222a]">
          <label className="block text-[11px] font-medium uppercase tracking-wide text-slate-400">
            Name
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-indigo-900/40"
          />

          <div className="mt-3 flex items-center justify-between">
            <label className="block text-[11px] font-medium uppercase tracking-wide text-slate-400">
              Description
            </label>
            <button
              type="button"
              onClick={suggest}
              disabled={suggesting || saving}
              title="Draft from this KB's documents"
              className="inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 dark:border-indigo-900 dark:bg-indigo-950/50 dark:text-indigo-300 dark:hover:bg-indigo-950"
            >
              {suggesting ? <Spinner size={11} /> : <Sparkles size={11} />}
              Suggest
            </button>
          </div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="What this KB uniquely holds — the router reads it to route questions here. When two KBs share vocabulary, say what sets them apart."
            className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:ring-indigo-900/40"
          />

          <label className="mt-3 block text-[11px] font-medium uppercase tracking-wide text-slate-400">
            Custom instructions
          </label>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={3}
            placeholder="Extra guidance for answers in this KB (tone, focus, format) — e.g. « cite les numéros d'article ». Added on top of the built-in rules; it can't override them."
            className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:ring-indigo-900/40"
          />

          <label className="mt-3 block text-[11px] font-medium uppercase tracking-wide text-slate-400">
            Number locale
          </label>
          <input
            value={locale}
            onChange={(e) => setLocale(e.target.value)}
            placeholder="fr · de · en · es · (blank = auto)"
            className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm placeholder:text-slate-300 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-600 dark:focus:ring-indigo-900/40"
          />

          <label className="mt-3 flex items-center gap-2.5 text-sm text-slate-700 dark:text-slate-300">
            <button
              type="button"
              onClick={() => setVerify((v) => !v)}
              className={`relative h-5 w-9 rounded-full transition-colors ${
                verify ? "bg-indigo-600" : "bg-slate-300"
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${
                  verify ? "left-4" : "left-0.5"
                }`}
              />
            </button>
            <span className="inline-flex items-center gap-1">
              <ShieldCheck size={14} className="text-slate-400" />
              Verify numbers against sources
            </span>
          </label>

          {error && <div className="mt-2 text-xs text-red-600">{error}</div>}

          <div className="mt-3.5 flex justify-end">
            <button
              onClick={save}
              disabled={!dirty || saving || !name.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-indigo-500 disabled:bg-indigo-300"
            >
              {saving ? <Spinner size={13} /> : <Check size={13} />} Save changes
            </button>
          </div>

          <div className="mt-3 border-t border-slate-100 pt-3 dark:border-slate-700">
            {!confirming ? (
              <button
                onClick={() => setConfirming(true)}
                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-red-600 hover:text-red-700 dark:text-red-400"
              >
                <Trash2 size={13} /> Delete this knowledge base
              </button>
            ) : (
              <div className="rounded-lg bg-red-50 p-2.5 dark:bg-red-950/40">
                <div className="text-[12px] text-red-700 dark:text-red-300">
                  Delete <span className="font-semibold">{kb.name}</span> and all
                  its documents, vectors and chat history? This cannot be undone.
                </div>
                <div className="mt-2 flex justify-end gap-1.5">
                  <button
                    onClick={() => setConfirming(false)}
                    disabled={deleting}
                    className="rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-slate-500 hover:bg-white"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={remove}
                    disabled={deleting}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-red-700 disabled:bg-red-300"
                  >
                    {deleting ? <Spinner size={13} /> : <Trash2 size={13} />}
                    Delete permanently
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
