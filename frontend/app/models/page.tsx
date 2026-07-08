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
  getModelRoles,
  pullModel,
  updateModelRole,
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
          <SlidersHorizontal size={20} className="text-slate-400" />
          Model Providers
        </h1>
        <p className="mt-0.5 max-w-2xl text-sm text-slate-500">
          Four abstract roles, each mapped to an endpoint you control. Nothing
          is hardcoded — pick installed Ollama models or pull new ones, per
          role. In local-only deployments every endpoint stays on your
          infrastructure.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
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
    <Card className="p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
            <Icon size={17} />
          </div>
          <div>
            <div className="text-sm font-semibold">{meta.title}</div>
            <div className="text-[11px] uppercase tracking-wide text-slate-400">
              {role.provider}
              {role.overridden && " · runtime override"}
            </div>
          </div>
        </div>
        <span
          title={role.detail}
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${
            role.ok
              ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
              : "bg-red-50 text-red-700 ring-1 ring-red-200"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${role.ok ? "bg-emerald-500" : "bg-red-500"}`}
          />
          {role.ok ? "healthy" : "unreachable"}
        </span>
      </div>

      <p className="mb-4 text-xs leading-5 text-slate-500">{meta.hint}</p>

      {role.provider === "disabled" ? (
        <div className="rounded-lg bg-slate-50 px-3 py-2.5 text-xs text-slate-500">
          Disabled by configuration. Enable it via
          <code className="mx-1 rounded bg-slate-100 px-1 py-0.5">
            LEDGERRAG_MODELS__{role.role.toUpperCase()}__PROVIDER
          </code>
          when the phase that uses it lands.
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">
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
            <label className="mb-1 block text-xs font-medium text-slate-600">
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
    <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
      <div className="mb-2 text-xs font-medium text-slate-600">
        Install a new model on this endpoint
      </div>
      <div className="flex gap-2">
        <input
          className={`${inputCls} bg-white`}
          placeholder="e.g. qwen3-vl:8b-instruct"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={pulling}
        />
        <Button
          variant="secondary"
          onClick={pull}
          disabled={pulling || !name.trim()}
          className="shrink-0"
        >
          {pulling ? <Spinner size={14} /> : <Download size={14} />}
          Pull
        </Button>
      </div>
      {(status || percent !== null) && (
        <div className="mt-2">
          {percent !== null && (
            <div className="mb-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all"
                style={{ width: `${percent}%` }}
              />
            </div>
          )}
          <div className="text-[11px] text-slate-500">
            {status}
            {percent !== null && ` · ${percent}%`}
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}
