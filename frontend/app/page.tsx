"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FolderPlus,
  Globe,
  Plus,
} from "lucide-react";
import { createKb, getKbs, type KB, type KBDocStatus } from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  Field,
  Modal,
  Spinner,
  inputCls,
} from "@/components/ui";
import KbCardMenu from "@/components/KbCardMenu";

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

  const refresh = useCallback(
    () =>
      getKbs()
        .then(setKbs)
        .catch((e) => setError(String(e))),
    [],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  // keep the list's status badges live while any KB is still ingesting, the
  // same way DocumentsPanel polls inside a KB — so "processing → ready/failed"
  // updates here without a manual reload
  const anyProcessing = (kbs ?? []).some(
    (k) => (k.doc_status?.processing ?? 0) > 0,
  );
  useEffect(() => {
    if (!anyProcessing) return;
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [anyProcessing, refresh]);

  return (
    <div>
      {/* wraps rather than overflowing: at 390px the heading and the button
          cannot share a row, and a page that scrolls sideways to reach its
          primary action is worse than one that stacks */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight">Knowledge Bases</h1>
          <p className="mt-0.5 text-sm text-ink-muted">
            Each knowledge base is an isolated corpus with its own documents.
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus size={16} aria-hidden="true" /> New knowledge base
        </Button>
      </div>

      {error && (
        <div className="callout callout-danger mb-4">
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
          hint="Create one, then drop your documents on it — policies, reports, anything with tables."
          action={
            <Button onClick={() => setShowCreate(true)}>
              <Plus size={16} aria-hidden="true" /> New knowledge base
            </Button>
          }
        />
      ) : (
        <div className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {kbs.map((kb) => (
            <div key={kb.id} className="group relative">
              <Link href={`/kb/${kb.id}`}>
                <Card className="lift h-full p-4">
                  <div className="mb-3 flex items-start justify-between">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 transition-colors group-hover:bg-indigo-600 group-hover:text-white dark:bg-indigo-950/60 dark:text-indigo-300 dark:group-hover:bg-indigo-500 dark:group-hover:text-white">
                      <Database size={18} />
                    </div>
                    {kb.config?.locale && (
                      <span className="mr-8 inline-flex items-center gap-1 rounded-full bg-surface-sunken px-2 py-0.5 text-[11px] font-medium uppercase text-ink-muted">
                        <Globe size={11} /> {kb.config.locale}
                      </span>
                    )}
                  </div>
                  <div className="font-display text-[16px] font-bold tracking-[0.005em] text-ink transition-colors group-hover:text-indigo-700 dark:group-hover:text-indigo-300">
                    {kb.name}
                  </div>
                  <p className="mt-1 line-clamp-2 min-h-[2rem] text-[13px] leading-5 text-ink-muted">
                    {kb.description || "No description — add one, the router will use it."}
                  </p>
                  <IngestProgress s={kb.doc_status} />
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <KbStatus s={kb.doc_status} />
                    <span className="shrink-0 text-[11px] text-ink-subtle">
                      {new Date(kb.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </Card>
              </Link>
              <div className="absolute right-3 top-3">
                <KbCardMenu kb={kb} onChanged={refresh} />
              </div>
            </div>
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

const plural = (n: number) => (n === 1 ? "" : "s");

/** How far ingestion got, from the counts the list already returns.
 *
 *  Only while the worker actually has something in flight. A bar sitting at
 *  100% on every finished corpus is a rule pretending to be information — the
 *  pills below already say "40 ready". Here, motion on a card means work is
 *  happening on it right now. */
function IngestProgress({ s }: { s?: KBDocStatus | null }) {
  if (!s || s.total === 0 || s.processing === 0) return null;
  const settled = s.done + s.failed;
  return (
    <div
      className="progress is-live mt-3"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={s.total}
      aria-valuenow={settled}
      aria-label={`${settled} of ${s.total} documents processed`}
    >
      <i style={{ width: `${Math.round((settled / s.total) * 100)}%` }} />
    </div>
  );
}

// Aggregate ingestion state of a KB, shown on its list card. One pill per
// non-zero state (processing / failed / ready) so a glance answers "is it done,
// still parsing, or did something fail?" without opening the KB.
function KbStatus({ s }: { s?: KBDocStatus | null }) {
  if (!s || s.total === 0)
    return (
      <span className="text-[11px] text-ink-subtle">
        No documents
      </span>
    );

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {s.processing > 0 && (
        <span
          className="pill pill-info"
          title={`${s.processing} document${plural(s.processing)} still parsing`}
        >
          <span className="relative flex h-1.5 w-1.5" aria-hidden="true">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
          </span>
          {s.processing} processing
        </span>
      )}
      {s.failed > 0 && (
        <span
          className="pill pill-danger"
          title={`${s.failed} document${plural(s.failed)} failed to process`}
        >
          <AlertTriangle size={11} aria-hidden="true" /> {s.failed} failed
        </span>
      )}
      {s.done > 0 && (
        <span
          className="pill pill-ok"
          title={`${s.done} document${plural(s.done)} ready`}
        >
          <CheckCircle2 size={11} aria-hidden="true" /> {s.done} ready
        </span>
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
  const [verify, setVerify] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createKb(name.trim(), description.trim(), locale || null, verify);
      onCreated();
    } catch (err) {
      setError(String(err));
      setBusy(false);
    }
  };

  return (
    <Modal title="New knowledge base" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name">
          <input
            className={inputCls}
            placeholder="e.g. HR policies"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </Field>
        <Field
          label="Description"
          hint="Used later to route a question to the right knowledge base, so describe what it holds rather than what it is called."
        >
          <textarea
            className={`${inputCls} resize-none`}
            rows={3}
            placeholder="e.g. Collective agreements and pay scales, 2019 onwards."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <Field
          label="Number locale of the documents"
          hint="How numbers are printed in your documents. Declaring it avoids guessing when normalizing table values."
        >
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
        </Field>
        <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-line p-3">
          <input
            type="checkbox"
            checked={verify}
            onChange={(e) => setVerify(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-line-strong text-indigo-600"
          />
          <span className="text-xs leading-4 text-ink-muted">
            <span className="font-medium text-ink">
              Verify numbers in answers
            </span>
            <br />
            Cross-check every figure in an answer against the cited sources and
            warn on any that can&apos;t be matched. Recommended for tables.
          </span>
        </label>
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
