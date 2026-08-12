"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Settings2, Trash2, Check, ShieldCheck, Sparkles } from "lucide-react";
import { updateKb, deleteKb, suggestDescription, type KB } from "@/lib/api";
import CopyButton from "@/components/CopyButton";
import { Button, Spinner } from "@/components/ui";

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
  const [contact, setContact] = useState(
    kb.config?.escalation_contact ?? "",
  );
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
        escalation_contact: contact.trim(),
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
      <Button
        size="sm"
        variant="tonal"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        icon={<Settings2 size={14} />}
        title="Knowledge base settings"
      >
        Settings
      </Button>

      {open && (
        <div className="pop absolute right-0 z-20 mt-1.5 w-96 max-w-[90vw] origin-top-right rounded-xl border border-line bg-surface p-3.5 shadow-lift">
          <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
            Name
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-line-strong px-2.5 py-1.5 text-sm bg-surface text-ink focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />

          <div className="mt-3 flex items-center justify-between">
            <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
              Description
            </label>
            <Button
              size="xs"
              variant="tonal"
              onClick={suggest}
              disabled={saving}
              loading={suggesting}
              icon={<Sparkles size={11} />}
              title="Draft from this KB's documents"
            >
              Suggest
            </Button>
          </div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="What this KB uniquely holds — the router reads it to route questions here. When two KBs share vocabulary, say what sets them apart."
            className="mt-1 w-full rounded-lg border border-line-strong px-2.5 py-1.5 text-sm placeholder:text-ink-subtle bg-surface text-ink focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />

          <div className="mt-3 flex items-center justify-between">
            <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
              Operator instructions
            </label>
            <span
              title="These guide tone, focus and format only. The built-in safety rules — answer only from the cited sources, quote numbers exactly, and say when the answer isn't in the documents — always win."
              className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-800/60"
            >
              <ShieldCheck size={11} /> Safety core protected
            </span>
          </div>
          {/* prompts are code — mono reads right, and the chip above makes the
              immutable-core guarantee legible (they layer on, never override) */}
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={4}
            placeholder="Extra guidance for answers in this KB (tone, focus, format) — e.g. « cite les numéros d'article ». Layered on top of the built-in rules; it can never relax them."
            className="mt-1 w-full rounded-lg border border-line-strong px-2.5 py-1.5 font-mono text-[12px] leading-relaxed placeholder:font-sans placeholder:text-[11px] placeholder:text-ink-subtle bg-surface text-ink focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />

          <label className="mt-3 block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
            Number locale
          </label>
          <input
            value={locale}
            onChange={(e) => setLocale(e.target.value)}
            placeholder="fr · de · en · es · (blank = auto)"
            className="mt-1 w-full rounded-lg border border-line-strong px-2.5 py-1.5 text-sm placeholder:text-ink-subtle bg-surface text-ink focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />

          <label className="mt-3 block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
            Contact en cas de doute
          </label>
          <input
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder="ex. service RH du CETIAT"
            className="mt-1 w-full rounded-lg border border-line-strong px-2.5 py-1.5 text-sm placeholder:text-ink-subtle bg-surface text-ink focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />
          <p className="mt-1 text-[11px] text-ink-subtle">
            Affiché quand une réponse s&apos;appuie sur la lecture d&apos;une
            image ou sur une source peu fiable. Vide = formulation générique.
          </p>

          <label className="mt-3 flex items-center gap-2.5 text-sm text-ink">
            {/* a real switch: announced as one, and its knob slides on a
                transform rather than animating `left` */}
            <button
              type="button"
              role="switch"
              aria-checked={verify}
              onClick={() => setVerify((v) => !v)}
              className={`relative h-5 w-9 shrink-0 rounded-full transition-colors duration-200 ${
                verify ? "bg-indigo-600" : "bg-line-strong"
              }`}
            >
              <span
                aria-hidden="true"
                className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                  verify ? "translate-x-4" : "translate-x-0"
                }`}
                style={{ transitionTimingFunction: "cubic-bezier(.2,.9,.25,1)" }}
              />
            </button>
            <span className="inline-flex items-center gap-1">
              <ShieldCheck size={14} className="text-ink-subtle" />
              Verify numbers against sources
            </span>
          </label>

          {error && <div className="mt-2 text-xs text-red-600">{error}</div>}

          <div className="mt-3.5 flex justify-end">
            <Button
              size="sm"
              onClick={save}
              disabled={!dirty || !name.trim()}
              loading={saving}
              icon={<Check size={13} />}
            >
              Save changes
            </Button>
          </div>

          {/* the id is what the API and the eval gates are addressed by, and
              reading it out of the address bar to retype it is a chore */}
          <div className="mt-3 border-t border-line pt-3">
            <div className="text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
              Knowledge base id
            </div>
            <div className="mt-1 flex items-center gap-1">
              <code className="min-w-0 flex-1 truncate rounded-md bg-surface-sunken px-2 py-1 font-mono text-[11px] text-ink-muted">
                {kb.id}
              </code>
              <CopyButton text={kb.id} title="Copy the knowledge base id" />
            </div>
            <div className="mt-1 text-[11px] text-ink-subtle">
              For the API and the eval gates —{" "}
              <span className="font-mono">make eval-qa KB=…</span>
            </div>
          </div>

          <div className="mt-3 border-t border-line pt-3">
            {!confirming ? (
              <Button
                size="xs"
                variant="ghost"
                onClick={() => setConfirming(true)}
                icon={<Trash2 size={13} />}
                className="!text-red-700 hover:!bg-red-50 dark:!text-red-400 dark:hover:!bg-red-950/40"
              >
                Delete this knowledge base
              </Button>
            ) : (
              <div className="rounded-lg bg-red-50 p-2.5 dark:bg-red-950/40">
                <div className="text-[12px] text-red-700 dark:text-red-300">
                  Delete <span className="font-semibold">{kb.name}</span> and all
                  its documents, vectors and chat history? This cannot be undone.
                </div>
                <div className="mt-2 flex justify-end gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setConfirming(false)}
                    disabled={deleting}
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={remove}
                    loading={deleting}
                    icon={<Trash2 size={13} />}
                  >
                    Delete permanently
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
