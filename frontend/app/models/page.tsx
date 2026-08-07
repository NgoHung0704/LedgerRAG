"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Braces,
  Check,
  Download,
  Eye,
  MessageSquareText,
  ScanSearch,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";
import {
  formatBytes,
  getAvailableModels,
  getChatInstructions,
  getModelRoles,
  pullModel,
  setChatInstructions,
  updateModelRole,
  type ChatPersona,
  type ModelRole,
  type OllamaModel,
} from "@/lib/api";
import { Button, Card, Spinner, inputCls } from "@/components/ui";

const ROLE_META: Record<
  ModelRole["role"],
  { title: string; hint: string; icon: LucideIcon }
> = {
  parser: {
    title: "Parser / OCR (VLM)",
    hint: "Reads tables and scanned pages during ingestion — the accuracy-critical role. Validate any change with `make eval-tables`.",
    icon: Eye,
  },
  embedder: {
    title: "Embedder",
    hint: "Turns chunks, records and summaries into vectors for retrieval. Changing it requires re-indexing documents.",
    icon: Braces,
  },
  chat: {
    title: "Chat (LLM)",
    hint: "Generates answers and table summaries, in the user's language.",
    icon: MessageSquareText,
  },
  reranker: {
    title: "Reranker",
    hint: "Optional result reordering (Phase 4). Leave disabled until then.",
    icon: ScanSearch,
  },
};

export default function ModelsPage() {
  const [roles, setRoles] = useState<ModelRole[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    () =>
      getModelRoles()
        .then(setRoles)
        .catch((e) => setError(String(e))),
    [],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div>
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <SlidersHorizontal size={20} className="text-ink-subtle" />
          Model Providers
        </h1>
        <p className="mt-0.5 max-w-2xl text-sm text-ink-muted">
          Four abstract roles, each mapped to an endpoint you control. Nothing
          is hardcoded — pick installed Ollama models or pull new ones, per
          role. In local-only deployments every endpoint stays on your
          infrastructure.
        </p>
      </div>

      <GlobalInstructions />

      {error && (
        <div className="callout callout-danger mb-4">
          {error}
        </div>
      )}

      {roles === null ? (
        <div className="flex justify-center py-16">
          <Spinner size={22} />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {roles.map((role) => (
            <RoleCard key={role.role} role={role} onChanged={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}

// The global chat persona: who the assistant says it is (this is what answers
// "who are you?", with no retrieval), plus extra guidance added on top of the
// built-in answering rules. Both additive — they can't relax the rules that
// keep numbers exact. Saving is admin-gated server-side.
function GlobalInstructions() {
  const [persona, setPersona] = useState<ChatPersona | null>(null);
  const [saved, setSaved] = useState<ChatPersona>({ identity: "", text: "" });
  const [saving, setSaving] = useState(false);
  const [ok, setOk] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getChatInstructions()
      .then((r) => {
        setPersona(r);
        setSaved(r);
      })
      .catch(() => {
        setPersona({ identity: "", text: "" });
      });
  }, []);

  const dirty =
    persona !== null &&
    (persona.identity !== saved.identity || persona.text !== saved.text);

  const save = async () => {
    if (persona === null) return;
    setSaving(true);
    setError(null);
    try {
      const r = await setChatInstructions(persona);
      setSaved(r);
      setPersona(r);
      setOk(true);
      setTimeout(() => setOk(false), 2000);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="mb-4 p-4">
      <div className="mb-1 flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-sunken text-ink-muted">
          <MessageSquareText size={17} />
        </div>
        <div>
          <div className="text-sm font-semibold">Chat persona (global)</div>
          <div className="text-[11px] uppercase tracking-wide text-ink-subtle">
            applies to every conversation
          </div>
        </div>
      </div>

      {persona === null ? (
        <div className="flex justify-center py-6">
          <Spinner size={18} />
        </div>
      ) : (
        <>
          <label className="mt-2 block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
            Identity — who the assistant is
          </label>
          <p className="mb-1 text-xs leading-5 text-ink-muted">
            Used when someone asks « qui es-tu ? » — answered directly, without
            searching the documents. Leave empty for the built-in description.
          </p>
          <textarea
            value={persona.identity}
            onChange={(e) =>
              setPersona({ ...persona, identity: e.target.value })
            }
            rows={3}
            placeholder="e.g. l'assistant documentaire RH du CETIAT : tu réponds aux questions sur les accords et conventions, en citant toujours tes sources."
            className={`${inputCls} font-sans`}
          />

          <label className="mt-3 block text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
            Instructions — how it should answer
          </label>
          <p className="mb-1 text-xs leading-5 text-ink-muted">
            Shapes tone, focus and format for every knowledge base. It cannot
            override the rules that keep numbers exact and answers grounded in
            the sources. A KB can add its own in its Settings.
          </p>
          <textarea
            value={persona.text}
            onChange={(e) => setPersona({ ...persona, text: e.target.value })}
            rows={3}
            placeholder="e.g. Répondez de façon concise et professionnelle ; citez les numéros d'article quand ils existent."
            className={`${inputCls} font-sans`}
          />

          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
          <div className="mt-2 flex justify-end">
            <Button
              onClick={save}
              disabled={!dirty || saving}
              variant={dirty ? "primary" : "secondary"}
            >
              {ok ? (
                <>
                  <Check size={15} /> Saved
                </>
              ) : saving ? (
                "Saving…"
              ) : (
                "Save"
              )}
            </Button>
          </div>
        </>
      )}
    </Card>
  );
}

function RoleCard({
  role,
  onChanged,
}: {
  role: ModelRole;
  onChanged: () => void;
}) {
  const meta = ROLE_META[role.role];
  const Icon = meta.icon;
  const [available, setAvailable] = useState<OllamaModel[] | null>(null);
  const [selected, setSelected] = useState(role.model_name);
  const [baseUrl, setBaseUrl] = useState(role.base_url);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isOllama = role.provider === "ollama";

  useEffect(() => {
    if (isOllama) {
      getAvailableModels(role.role)
        .then(setAvailable)
        .catch(() => setAvailable([]));
    }
  }, [role.role, role.base_url, isOllama]);

  const dirty = selected !== role.model_name || baseUrl !== role.base_url;

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateModelRole(role.role, {
        model_name: selected,
        base_url: baseUrl,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onChanged();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="lift p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          {/* the tile carries the role's health, so the card answers "is this
              one working?" before you read a word of it */}
          <div
            className={`flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${
              role.provider === "disabled"
                ? "bg-surface-sunken text-ink-subtle"
                : role.ok
                  ? "bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-300"
                  : "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-400"
            }`}
          >
            <Icon size={17} />
          </div>
          <div>
            <div className="text-sm font-semibold">{meta.title}</div>
            <div className="text-[11px] uppercase tracking-wide text-ink-subtle">
              {role.provider}
              {role.overridden && " · runtime override"}
            </div>
          </div>
        </div>
        <span
          title={role.detail}
          className={`pill ${role.ok ? "pill-ok" : "pill-danger"} py-1`}
        >
          <span className="relative flex h-1.5 w-1.5" aria-hidden="true">
            {/* a reachable endpoint is a live thing, and says so quietly */}
            {role.ok && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" />
            )}
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
          </span>
          {role.ok ? "healthy" : "unreachable"}
        </span>
      </div>

      <p className="mb-4 text-xs leading-5 text-ink-muted">{meta.hint}</p>

      {role.provider === "disabled" ? (
        <div className="rounded-lg bg-surface-sunken px-3 py-2.5 text-xs text-ink-muted dark:bg-slate-800/60">
          Disabled by configuration. Enable it via
          <code className="mx-1 rounded bg-surface-sunken px-1 py-0.5">
            LEDGERRAG_MODELS__{role.role.toUpperCase()}__PROVIDER
          </code>
          when the phase that uses it lands.
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-muted">
              Endpoint
            </label>
            <input
              className={inputCls}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://localhost:11434"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-muted">
              Model
            </label>
            {isOllama && available !== null && available.length > 0 ? (
              <select
                className={inputCls}
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                {!available.some((m) => m.name === selected) && (
                  <option value={selected}>{selected} (not installed)</option>
                )}
                {available.map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.name}
                    {m.parameter_size ? ` · ${m.parameter_size}` : ""}
                    {m.size_bytes ? ` · ${formatBytes(m.size_bytes)}` : ""}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className={inputCls}
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                placeholder="model name"
              />
            )}
          </div>

          <div className="flex items-center justify-between">
            <Button
              onClick={save}
              disabled={!dirty || saving}
              variant={dirty ? "primary" : "secondary"}
            >
              {saved ? (
                <>
                  <Check size={15} /> Saved
                </>
              ) : saving ? (
                "Saving…"
              ) : (
                "Save"
              )}
            </Button>
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}

          {isOllama && <PullBox role={role.role} onPulled={onChanged} />}
        </div>
      )}
    </Card>
  );
}

function PullBox({
  role,
  onPulled,
}: {
  role: string;
  onPulled: () => void;
}) {
  const [name, setName] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [percent, setPercent] = useState<number | null>(null);
  const [pulling, setPulling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pull = async () => {
    const model = name.trim();
    if (!model || pulling) return;
    setPulling(true);
    setError(null);
    setStatus("starting…");
    setPercent(null);
    try {
      for await (const ev of pullModel(role, model)) {
        if (ev.type === "progress") {
          setStatus(ev.status);
          if (ev.total && ev.completed != null) {
            setPercent(Math.round((ev.completed / ev.total) * 100));
          }
        } else if (ev.type === "done") {
          setStatus(`pulled ${ev.name}`);
          setPercent(100);
          setName("");
          onPulled();
        } else if (ev.type === "error") {
          setError(ev.message);
          setStatus(null);
        }
      }
    } catch (e) {
      setError(String(e));
      setStatus(null);
    } finally {
      setPulling(false);
    }
  };

  return (
    <div className="rounded-lg border border-line bg-surface-sunken p-3">
      <div className="mb-2 text-xs font-medium text-ink-muted">
        Install a new model on this endpoint
      </div>
      <div className="flex gap-2">
        <input
          className={inputCls}
          placeholder="e.g. qwen3-vl:8b-instruct"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={pulling}
        />
        <Button
          variant="tonal"
          onClick={pull}
          disabled={!name.trim()}
          loading={pulling}
          icon={<Download size={14} />}
          className="shrink-0"
        >
          Pull
        </Button>
      </div>
      {(status || percent !== null) && (
        <div className="mt-2.5">
          {percent !== null && (
            // the sweep runs while bytes are still arriving, and stops when
            // they stop — a download that has stalled should look stalled
            <div className={`progress mb-1.5 ${pulling ? "is-live" : ""}`}>
              <i style={{ width: `${percent}%` }} />
            </div>
          )}
          <div className="text-[11px] text-ink-muted">
            {status}
            {percent !== null && ` · ${percent}%`}
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}
