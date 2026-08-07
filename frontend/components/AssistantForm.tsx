"use client";

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
            Name
          </label>
          <input
            className={inputCls}
            placeholder="e.g. Assistant RH"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            Description
          </label>
          <input
            className={inputCls}
            placeholder="What it helps with — also how it introduces itself."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            Knowledge bases it can search
          </label>
          {kbs.length === 0 ? (
            <p className="text-xs text-ink-subtle">
              No knowledge base exists yet.
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
                      {kb.description || "No description"}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          )}
          <p className="mt-1 text-[11px] leading-4 text-ink-subtle">
            With several, the router picks the relevant one(s) per question —
            among these only, never the rest of your workspace.
          </p>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            Instructions
          </label>
          <textarea
            className={`${inputCls} resize-none`}
            rows={4}
            placeholder="How it should answer — e.g. « Réponds de façon concise et cite les numéros d'article. »"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
          <p className="mt-1 text-[11px] leading-4 text-ink-subtle">
            Added on top of the built-in rules: it shapes tone and focus but
            can&apos;t loosen quoting numbers exactly or citing sources.
          </p>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            Opening message
          </label>
          <input
            className={inputCls}
            placeholder="Shown in an empty conversation, e.g. « Bonjour, que puis-je chercher pour vous ? »"
            value={opening}
            onChange={(e) => setOpening(e.target.value)}
          />
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
              Verify numbers in answers
            </span>
            <br />
            Cross-check every figure against the cited sources and warn on any
            that can&apos;t be matched.
          </span>
        </label>

        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex items-center gap-2 border-t border-line pt-3">
          {onDelete &&
            (confirmingDelete ? (
              <div className="flex items-center gap-2 text-xs text-red-700 dark:text-red-300">
                Delete this assistant and its conversations?
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
                  Delete
                </Button>
                <Button
                  type="button"
                  size="xs"
                  variant="ghost"
                  onClick={() => setConfirmingDelete(false)}
                >
                  Cancel
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
                Delete assistant
              </Button>
            ))}
          <div className="ml-auto flex gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || !name.trim()}>
              {busy ? <Spinner size={14} /> : null}
              {assistant ? "Save changes" : "Create"}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
