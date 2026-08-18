"use client";

import { createEmbedToken } from "@/lib/api";
import { useT } from "@/components/LocaleProvider";
import { useState } from "react";
import { Database, ShieldCheck, Trash2 } from "lucide-react";
import type { Assistant, AssistantInput, KB } from "@/lib/api";
import { Button, Modal, Spinner, inputCls } from "@/components/ui";

/** Create/edit an assistant: its context (which knowledge bases it may search),
 * its instructions, and how it greets. Shared by the list page and the
 * assistant's own Settings so both stay identical. */
export default function AssistantForm({
  title,
  kbs,
  assistant,
  onClose,
  onSubmit,
  onDelete,
}: {
  title: string;
  kbs: KB[];
  assistant?: Assistant;
  onClose: () => void;
  onSubmit: (values: AssistantInput) => Promise<void>;
  onDelete?: () => Promise<void>;
}) {
  const t = useT();
  const [name, setName] = useState(assistant?.name ?? "");
  const [description, setDescription] = useState(assistant?.description ?? "");
  const [instructions, setInstructions] = useState(
    assistant?.instructions ?? "",
  );
  const [opening, setOpening] = useState(assistant?.opening_message ?? "");
  const [kbIds, setKbIds] = useState<Set<string>>(
    new Set(assistant?.kb_ids ?? []),
  );
  const [verify, setVerify] = useState<boolean>(assistant?.verify ?? true);
  const [contact, setContact] = useState(assistant?.escalation_contact ?? "");
  const [token, setToken] = useState(assistant?.embed_token ?? "");
  const [minting, setMinting] = useState(false);

  /** The token comes from the server; see createEmbedToken. */
  const mint = async (id: string) => {
    setMinting(true);
    try {
      setToken((await createEmbedToken(id)).embed_token);
    } catch (err) {
      setError(String(err));
    } finally {
      setMinting(false);
    }
  };

  /** What the host application pastes. `origin` is read at render because the
   *  deployment's own address is the only one that can be right here, and it is
   *  not known at build time. */
  const snippet = (tok: string) =>
    `<iframe src="${typeof window === "undefined" ? "" : window.location.origin}` +
    `/embed/${tok}?lang=fr" width="420" height="620" ` +
    `style="border:1px solid #e5e7eb;border-radius:12px"></iframe>`;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const toggle = (id: string) =>
    setKbIds((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim(),
        instructions: instructions.trim(),
        opening_message: opening.trim(),
        kb_ids: Array.from(kbIds),
        verify,
        escalation_contact: contact.trim(),
        embed_token: token.trim(),
      });
    } catch (err) {
      setError(String(err));
      setBusy(false);
    }
  };

  return (
    <Modal title={title} onClose={onClose} wide>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            {t("kb.field_name")}
          </label>
          <input
            className={inputCls}
            placeholder={t("asst.name_placeholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            {t("kb.field_description")}
          </label>
          <input
            className={inputCls}
            placeholder={t("asst.description_placeholder")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            {t("asst.kbs_it_can_search")}
          </label>
          {kbs.length === 0 ? (
            <p className="text-xs text-ink-subtle">
              {t("asst.no_kb_exists")}
            </p>
          ) : (
            <div className="max-h-48 space-y-1 overflow-auto rounded-lg border border-line p-1.5">
              {kbs.map((kb) => (
                <label
                  key={kb.id}
                  className="flex cursor-pointer items-start gap-2.5 rounded px-2 py-1.5 hover:bg-surface-sunken dark:hover:bg-slate-800/60"
                >
                  <input
                    type="checkbox"
                    checked={kbIds.has(kb.id)}
                    onChange={() => toggle(kb.id)}
                    className="mt-0.5 h-4 w-4 rounded border-line-strong text-indigo-600"
                  />
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5 text-[13px] font-medium text-ink">
                      <Database size={12} className="text-ink-subtle" />
                      {kb.name}
                    </span>
                    <span className="line-clamp-1 text-[11px] text-ink-subtle">
                      {kb.description || t("kb.no_description_short")}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          )}
          <p className="mt-1 text-[11px] leading-4 text-ink-subtle">
            {t("asst.kbs_hint")}
          </p>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            {t("asst.instructions")}
          </label>
          <textarea
            className={`${inputCls} resize-none`}
            rows={4}
            placeholder={t("asst.instructions_placeholder")}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
          <p className="mt-1 text-[11px] leading-4 text-ink-subtle">
            {t("asst.instructions_hint")}
          </p>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            {t("asst.opening_message")}
          </label>
          <input
            className={inputCls}
            placeholder={t("asst.opening_placeholder")}
            value={opening}
            onChange={(e) => setOpening(e.target.value)}
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            {t("asst.escalation_contact")}
          </label>
          <input
            className={inputCls}
            placeholder={t("kb.contact_placeholder")}
            value={contact}
            onChange={(e) => setContact(e.target.value)}
          />
          <p className="mt-1 text-xs text-ink-subtle">
            {t("asst.escalation_contact_hint")}
          </p>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            {t("asst.embed")}
          </label>
          {!assistant ? (
            <p className="text-xs text-ink-subtle">{t("asst.embed_save_first")}</p>
          ) : token ? (
            <>
              <textarea
                readOnly
                rows={3}
                className={`${inputCls} font-mono text-[11px]`}
                onFocus={(e) => e.currentTarget.select()}
                value={snippet(token)}
              />
              <div className="mt-1 flex items-center gap-2">
                <Button type="button" size="xs" variant="ghost" loading={minting}
                        onClick={() => mint(assistant.id)}>
                  {t("asst.embed_regenerate")}
                </Button>
                <Button type="button" size="xs" variant="ghost"
                        onClick={() => setToken("")}>
                  {t("asst.embed_revoke")}
                </Button>
              </div>
              <p className="mt-1 text-xs text-ink-subtle">{t("asst.embed_hint")}</p>
            </>
          ) : (
            <Button type="button" size="xs" variant="tonal" loading={minting}
                    onClick={() => mint(assistant.id)}>
              {t("asst.embed_create")}
            </Button>
          )}
        </div>

        <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-line p-3">
          <input
            type="checkbox"
            checked={verify}
            onChange={(e) => setVerify(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-line-strong text-indigo-600"
          />
          <span className="text-xs leading-4 text-ink-muted">
            <span className="inline-flex items-center gap-1 font-medium text-ink">
              <ShieldCheck size={13} className="text-ink-subtle" />
              {t("kb.verify_numbers")}
            </span>
            <br />
            {t("asst.verify_hint")}
          </span>
        </label>

        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex items-center gap-2 border-t border-line pt-3">
          {onDelete &&
            (confirmingDelete ? (
              <div className="flex items-center gap-2 text-xs text-red-700 dark:text-red-300">
                {t("asst.delete_confirm")}
                <Button
                  type="button"
                  size="xs"
                  variant="destructive"
                  loading={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await onDelete();
                    } catch (err) {
                      setError(String(err));
                      setBusy(false);
                    }
                  }}
                >
                  {t("common.delete")}
                </Button>
                <Button
                  type="button"
                  size="xs"
                  variant="ghost"
                  onClick={() => setConfirmingDelete(false)}
                >
                  {t("common.cancel")}
                </Button>
              </div>
            ) : (
              <Button
                type="button"
                size="xs"
                variant="ghost"
                onClick={() => setConfirmingDelete(true)}
                icon={<Trash2 size={13} />}
                className="!text-red-700 hover:!bg-red-50 dark:!text-red-400 dark:hover:!bg-red-950/40"
              >
                {t("asst.delete")}
              </Button>
            ))}
          <div className="ml-auto flex gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={busy || !name.trim()}>
              {busy ? <Spinner size={14} /> : null}
              {assistant ? t("common.save_changes") : t("common.create")}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
