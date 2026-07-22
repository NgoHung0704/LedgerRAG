"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Settings2, Trash2, Check, ShieldCheck } from "lucide-react";
import { updateKb, deleteKb, type KB } from "@/lib/api";
import { Spinner } from "@/components/ui";

// Rename, change number locale, toggle verification, or delete the KB — the
// settings that were missing after creation.
export default function KbSettings({
  kb,
  onUpdated,
}: {
  kb: KB;
  onUpdated: (kb: KB) => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const [name, setName] = useState(kb.name);
  const [locale, setLocale] = useState(kb.config?.locale ?? "");
  const [verify, setVerify] = useState(kb.config?.verify ?? true);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

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
    (locale || "") !== (kb.config?.locale ?? "") ||
    verify !== (kb.config?.verify ?? true);

  const save = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const updated = await updateKb(kb.id, {
        name: name.trim(),
        locale: locale.trim(),
        verify,
      });
      onUpdated(updated);
      setOpen(false);
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
        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-slate-600 hover:border-indigo-300 hover:text-indigo-700"
      >
        <Settings2 size={14} /> Settings
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-1.5 w-80 rounded-xl border border-slate-200 bg-white p-3.5 shadow-lg">
          <label className="block text-[11px] font-medium uppercase tracking-wide text-slate-400">
            Name
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />

          <label className="mt-3 block text-[11px] font-medium uppercase tracking-wide text-slate-400">
            Number locale
          </label>
          <input
            value={locale}
            onChange={(e) => setLocale(e.target.value)}
            placeholder="fr · de · en · es · (blank = auto)"
            className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm placeholder:text-slate-300 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />

          <label className="mt-3 flex items-center gap-2.5 text-sm text-slate-700">
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

          <div className="mt-3.5 flex justify-end">
            <button
              onClick={save}
              disabled={!dirty || saving || !name.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-indigo-500 disabled:bg-indigo-300"
            >
              {saving ? <Spinner size={13} /> : <Check size={13} />} Save changes
            </button>
          </div>

          <div className="mt-3 border-t border-slate-100 pt-3">
            {!confirming ? (
              <button
                onClick={() => setConfirming(true)}
                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-red-600 hover:text-red-700"
              >
                <Trash2 size={13} /> Delete this knowledge base
              </button>
            ) : (
              <div className="rounded-lg bg-red-50 p-2.5">
                <div className="text-[12px] text-red-700">
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
