"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Bot, Database, Plus } from "lucide-react";
import {
  createAssistant,
  getAssistants,
  getKbs,
  type Assistant,
  type KB,
} from "@/lib/api";
import { Button, Card, EmptyState, Spinner } from "@/components/ui";
import AssistantForm from "@/components/AssistantForm";

// Assistants are chat apps: each one has its own knowledge bases (its context),
// its own instructions, and its own conversations. Knowledge bases stay
// independent — an assistant references them, so one corpus can back several.
export default function AssistantsPage() {
  const [assistants, setAssistants] = useState<Assistant[] | null>(null);
  const [kbs, setKbs] = useState<KB[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const refresh = useCallback(
    () =>
      getAssistants()
        .then(setAssistants)
        .catch((e) => setError(String(e))),
    [],
  );

  useEffect(() => {
    refresh();
    getKbs()
      .then(setKbs)
      .catch(() => setKbs([]));
  }, [refresh]);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Assistants</h1>
          <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
            A chat of its own: pick the knowledge bases it may search, tell it
            how to answer.
          </p>
        </div>
        <Button onClick={() => setCreating(true)} disabled={kbs.length === 0}>
          <Plus size={16} /> New assistant
        </Button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      {assistants === null ? (
        <div className="flex justify-center py-16">
          <Spinner size={22} />
        </div>
      ) : kbs.length === 0 ? (
        <EmptyState
          icon={<Database size={36} />}
          title="Create a knowledge base first"
          hint="An assistant answers from knowledge bases — add one with your documents, then come back and give it an assistant."
        />
      ) : assistants.length === 0 ? (
        <EmptyState
          icon={<Bot size={36} />}
          title="No assistants yet"
          hint="Create one: choose which knowledge bases it can search and write its instructions — e.g. an HR assistant over your agreements."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {assistants.map((a) => (
            <Link key={a.id} href={`/assistants/${a.id}`}>
              <Card className="group h-full p-4 transition-colors hover:border-indigo-300 dark:hover:border-indigo-700">
                <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-300">
                  <Bot size={18} />
                </div>
                <div className="font-serif text-[15px] font-semibold text-slate-900 group-hover:text-indigo-700 dark:text-slate-100 dark:group-hover:text-indigo-300">
                  {a.name}
                </div>
                <p className="mt-1 line-clamp-2 min-h-[2rem] text-[13px] leading-5 text-slate-500 dark:text-slate-400">
                  {a.description || "No description yet."}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  {a.kb_names.length === 0 ? (
                    <span className="text-[11px] text-amber-600 dark:text-amber-400">
                      No knowledge base attached
                    </span>
                  ) : (
                    a.kb_names.map((n) => (
                      <span
                        key={n}
                        className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                      >
                        <Database size={10} /> {n}
                      </span>
                    ))
                  )}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {creating && (
        <AssistantForm
          title="New assistant"
          kbs={kbs}
          onClose={() => setCreating(false)}
          onSubmit={async (values) => {
            await createAssistant(values);
            setCreating(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}
