"use client";

import { useT } from "@/components/LocaleProvider";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Settings2, Trash2, Check, ShieldCheck, Sparkles, Share2 } from "lucide-react";
import {
  updateKb,
  deleteKb,
  suggestDescription,
  createKbRetrievalKey,
  API_URL,
  type KB,
} from "@/lib/api";
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
  const t = useT();
  const router = useRouter();
  const [open, setOpen] = useState(defaultOpen);
  const ref = useRef<HTMLDivElement>(null);

  const [name, setName] = useState(kb.name);
  const [description, setDescription] = useState(kb.description ?? "");
  const [instructions, setInstructions] = useState(kb.config?.instructions ?? "");
  const [locale, setLocale] = useState(kb.config?.locale ?? "");
  const [verify, setVerify] = useState(kb.config?.verify ?? true);
  const [retrievalKey, setRetrievalKey] = useState(kb.retrieval_key ?? "");
  const [minting, setMinting] = useState(false);
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
    verify !== (kb.config?.verify ?? true) ||
    retrievalKey !== (kb.retrieval_key ?? "");

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
        retrieval_key: retrievalKey.trim(),
      });
      onUpdated(updated);
      setOpen(false);
    } catch {
      setError("Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  /** The key comes from the server; see createKbRetrievalKey. Minting
      persists immediately (no Save needed) — revoking clears it locally and
      takes effect on the next Save, same as the assistant embed token. */
  const mintRetrievalKey = async () => {
    setMinting(true);
    setError(null);
    try {
      const updated = await createKbRetrievalKey(kb.id);
      setRetrievalKey(updated.retrieval_key);
      onUpdated(updated);
    } catch {
      setError("Couldn't create the retrieval key. Please try again.");
    } finally {
      setMinting(false);
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
        title={t("kb.settings_title")}
      >
        {t("asst.settings")}
      </Button>

      {open && (
        <div className="pop max-h-[min(30rem,70vh)] overflow-y-auto absolute right-0 z-20 mt-1.5 w-96 max-w-[90vw] origin-top-right rounded-xl border border-line bg-surface p-3.5 shadow-lift">
          <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
            {t("kb.field_name")}
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-line-strong px-2.5 py-1.5 text-sm bg-surface text-ink focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />

          <div className="mt-3 flex items-center justify-between">
            <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
              {t("kb.field_description")}
            </label>
            <Button
              size="xs"
              variant="tonal"
              onClick={suggest}
              disabled={saving}
              loading={suggesting}
              icon={<Sparkles size={11} />}
              title={t("kb.suggest_hint")}
            >
              {t("kb.suggest")}
            </Button>
          </div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder={t("kb.description_router_placeholder")}
            className="mt-1 w-full rounded-lg border border-line-strong px-2.5 py-1.5 text-sm placeholder:text-ink-subtle bg-surface text-ink focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />

          <div className="mt-3 flex items-center justify-between">
            <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
              {t("kb.operator_instructions")}
            </label>
            <span
              title={t("kb.safety_core_hint")}
              className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-800/60"
            >
              <ShieldCheck size={11} /> {t("kb.safety_core")}
            </span>
          </div>
          {/* prompts are code — mono reads right, and the chip above makes the
              immutable-core guarantee legible (they layer on, never override) */}
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={4}
            placeholder={t("kb.instructions_placeholder")}
            className="mt-1 w-full rounded-lg border border-line-strong px-2.5 py-1.5 font-mono text-[12px] leading-relaxed placeholder:font-sans placeholder:text-[11px] placeholder:text-ink-subtle bg-surface text-ink focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />

          <label className="mt-3 block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
            {t("kb.number_locale")}
          </label>
          <input
            value={locale}
            onChange={(e) => setLocale(e.target.value)}
            placeholder="fr · de · en · es · (blank = auto)"
            className="mt-1 w-full rounded-lg border border-line-strong px-2.5 py-1.5 text-sm placeholder:text-ink-subtle bg-surface text-ink focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />


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
              {t("kb.verify_against_sources")}
            </span>
          </label>

          <div className="mt-3 border-t border-line pt-3">
            <label className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
              <Share2 size={11} /> {t("kb.retrieval_label")}
            </label>
            {retrievalKey ? (
              <>
                <textarea
                  readOnly
                  rows={3}
                  className="mt-1 w-full resize-none rounded-lg border border-line-strong px-2.5 py-1.5 font-mono text-[11px] leading-relaxed bg-surface text-ink"
                  onFocus={(e) => e.currentTarget.select()}
                  value={`Endpoint: ${API_URL}/api/retrieval/${kb.id}\nAPI Key:  ${retrievalKey}`}
                />
                <div className="mt-1 flex items-center gap-2">
                  <Button size="xs" variant="ghost" loading={minting}
                          onClick={mintRetrievalKey}>
                    {t("kb.retrieval_regenerate")}
                  </Button>
                  <Button size="xs" variant="ghost"
                          onClick={() => setRetrievalKey("")}>
                    {t("kb.retrieval_revoke")}
                  </Button>
                </div>
              </>
            ) : (
              <Button size="xs" variant="tonal" loading={minting}
                      onClick={mintRetrievalKey}>
                {t("kb.retrieval_enable")}
              </Button>
            )}
            <p className="mt-1 text-[11px] text-ink-subtle">{t("kb.retrieval_hint")}</p>
          </div>

          {error && <div className="mt-2 text-xs text-red-600">{error}</div>}

          <div className="mt-3.5 flex justify-end">
            <Button
              size="sm"
              onClick={save}
              disabled={!dirty || !name.trim()}
              loading={saving}
              icon={<Check size={13} />}
            >
              {t("common.save_changes")}
            </Button>
          </div>

          {/* the id is what the API and the eval gates are addressed by, and
              reading it out of the address bar to retype it is a chore */}
          <div className="mt-3 border-t border-line pt-3">
            <div className="text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
              {t("kb.id_label")}
            </div>
            <div className="mt-1 flex items-center gap-1">
              <code className="min-w-0 flex-1 truncate rounded-md bg-surface-sunken px-2 py-1 font-mono text-[11px] text-ink-muted">
                {kb.id}
              </code>
              <CopyButton text={kb.id} title={t("kb.id_copy")} />
            </div>
            <div className="mt-1 text-[11px] text-ink-subtle">
              {t("kb.id_hint")}{" "}
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
                {t("kb.delete_this")}
              </Button>
            ) : (
              <div className="rounded-lg bg-red-50 p-2.5 dark:bg-red-950/40">
                <div className="text-[12px] text-red-700 dark:text-red-300">
                  {t("kb.delete_confirm", { name: kb.name })}
                </div>
                <div className="mt-2 flex justify-end gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setConfirming(false)}
                    disabled={deleting}
                  >
                    {t("common.cancel")}
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={remove}
                    loading={deleting}
                    icon={<Trash2 size={13} />}
                  >
                    {t("kb.delete_permanently")}
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
