"use client";

import { useT } from "@/components/LocaleProvider";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Bot,
  Database,
  MessageSquare,
  Pencil,
  Plus,
  Settings2,
  Trash2,
} from "lucide-react";
import {
  deleteAssistant,
  deleteConversation,
  getAssistant,
  getConversationMessages,
  getConversations,
  getKbs,
  renameConversation,
  updateAssistant,
  type Assistant,
  type Conversation,
  type KB,
  type StoredMessage,
} from "@/lib/api";
import { Button, Spinner } from "@/components/ui";
import { confirm } from "@/components/confirm";
import AssistantForm from "@/components/AssistantForm";
import ChatPanel from "@/components/ChatPanel";

export default function AssistantPage({ params }: { params: { id: string } }) {
  const t = useT();
  const assistantId = params.id;
  const router = useRouter();
  const [assistant, setAssistant] = useState<Assistant | null>(null);
  const [kbs, setKbs] = useState<KB[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [replay, setReplay] = useState<StoredMessage[] | undefined>(undefined);
  const [loadingThread, setLoadingThread] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshConversations = useCallback(
    () =>
      getConversations(assistantId)
        .then(setConversations)
        .catch(() => {}),
    [assistantId],
  );

  useEffect(() => {
    getAssistant(assistantId)
      .then(setAssistant)
      .catch((e) => setError(String(e)));
    getKbs()
      .then(setKbs)
      .catch(() => setKbs([]));
    refreshConversations();
  }, [assistantId, refreshConversations]);

  const openConversation = async (sessionId: string) => {
    setLoadingThread(true);
    try {
      const { messages } = await getConversationMessages(sessionId);
      setReplay(messages);
      setCurrent(sessionId);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoadingThread(false);
    }
  };

  const newConversation = () => {
    setReplay(undefined);
    setCurrent(null);
  };

  const removeConversation = async (sessionId: string) => {
    if (
      !(await confirm({
        title: t("conv.delete_confirm"),
        message: t("conv.delete_body"),
        confirmLabel: t("common.delete"),
      }))
    )
      return;
    await deleteConversation(sessionId).catch((e) => setError(String(e)));
    if (current === sessionId) newConversation();
    refreshConversations();
  };

  const rename = async (c: Conversation) => {
    const title = window.prompt(t("conv.rename_prompt"), c.title);
    if (!title?.trim()) return;
    await renameConversation(c.session_id, title.trim()).catch((e) =>
      setError(String(e)),
    );
    refreshConversations();
  };

  if (error && !assistant) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
        {error}
      </div>
    );
  }
  if (!assistant) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size={22} />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <Link
        href="/assistants"
        className="mb-2 inline-flex items-center gap-1 text-xs text-ink-subtle hover:text-ink-muted"
      >
        <ArrowLeft size={13} /> {t("asst.title")}
      </Link>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-300">
          <Bot size={18} />
        </div>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight">
            {assistant.name}
          </h1>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            {assistant.kb_names.length === 0 ? (
              <span className="text-[11px] text-amber-600 dark:text-amber-400">
                {t("asst.no_kb_attached_settings")}
              </span>
            ) : (
              assistant.kb_names.map((n) => (
                <span
                  key={n}
                  className="inline-flex items-center gap-1 rounded-full bg-surface-sunken px-2 py-0.5 text-[11px] font-medium text-ink-muted"
                >
                  <Database size={10} /> {n}
                </span>
              ))
            )}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="tonal"
            icon={<Settings2 size={14} />}
            onClick={() => setEditing(true)}
          >
            {t("asst.settings")}
          </Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[260px_1fr]">
        {/* conversations */}
        <aside className="hidden min-h-0 flex-col rounded-xl border border-line bg-surface lg:flex">
          <div className="border-b border-line p-2">
            <Button
              size="sm"
              onClick={newConversation}
              icon={<Plus size={14} />}
              className="w-full"
            >
              {t("asst.new_conversation")}
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
            {conversations.length === 0 ? (
              <p className="px-2 py-3 text-[11px] leading-4 text-ink-subtle">
                {t("asst.no_conversation")}
              </p>
            ) : (
              conversations.map((c) => (
                <div
                  key={c.session_id}
                  className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 ${
                    current === c.session_id
                      ? "bg-indigo-50 dark:bg-indigo-950/50"
                      : "hover:bg-surface-sunken dark:hover:bg-slate-800/60"
                  }`}
                >
                  <button
                    onClick={() => openConversation(c.session_id)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <span
                      className={`flex items-center gap-1.5 truncate text-[13px] ${
                        current === c.session_id
                          ? "font-medium text-indigo-700 dark:text-indigo-300"
                          : "text-ink"
                      }`}
                    >
                      <MessageSquare size={12} className="shrink-0 text-ink-subtle" />
                      {c.title || t("conv.untitled")}
                    </span>
                    <span className="block pl-[18px] text-[10px] text-ink-subtle">
                      {new Date(c.updated_at).toLocaleDateString()}
                    </span>
                  </button>
                  {/* focus-visible, not just group-hover: these were invisible
                      to anyone arriving by keyboard */}
                  <button
                    onClick={() => rename(c)}
                    title={t("common.rename")}
                    aria-label={`Rename "${c.title}"`}
                    className="relative shrink-0 rounded p-1.5 text-ink-subtle opacity-0 transition-[opacity,color,transform] duration-150 after:absolute after:-inset-1 after:content-[''] hover:text-indigo-600 active:scale-95 focus-visible:opacity-100 group-hover:opacity-100 dark:hover:text-indigo-300"
                  >
                    <Pencil size={12} aria-hidden="true" />
                  </button>
                  <button
                    onClick={() => removeConversation(c.session_id)}
                    title={t("common.delete")}
                    aria-label={`Delete "${c.title}"`}
                    className="relative shrink-0 rounded p-1.5 text-ink-subtle opacity-0 transition-[opacity,color,transform] duration-150 after:absolute after:-inset-1 after:content-[''] hover:text-red-600 active:scale-95 focus-visible:opacity-100 group-hover:opacity-100 dark:hover:text-red-400"
                  >
                    <Trash2 size={12} aria-hidden="true" />
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* chat */}
        <div className="min-h-0">
          {loadingThread ? (
            <div className="flex h-full items-center justify-center rounded-xl border border-line">
              <Spinner size={20} />
            </div>
          ) : (
            <ChatPanel
              assistantId={assistantId}
              conversationId={current}
              initialMessages={replay}
              onSessionStarted={() => refreshConversations()}
              emptyState={
                <div className="flex h-full flex-col items-center justify-center px-6 text-center">
                  <Bot size={28} className="mb-3 text-ink-faint" />
                  <div className="max-w-md font-serif text-[15px] leading-relaxed text-ink">
                    {assistant.opening_message ||
                      `Ask ${assistant.name} anything about its documents.`}
                  </div>
                  <div className="mt-2 max-w-md text-xs leading-5 text-ink-subtle">
                    Answers are drawn only from{" "}
                    {assistant.kb_names.join(", ") || "its knowledge bases"}, with
                    citations you can open.
                  </div>
                </div>
              }
            />
          )}
        </div>
      </div>

      {editing && (
        <AssistantForm
          title={t("asst.settings_title")}
          kbs={kbs}
          assistant={assistant}
          onClose={() => setEditing(false)}
          onSubmit={async (values) => {
            const updated = await updateAssistant(assistantId, values);
            setAssistant(updated);
            setEditing(false);
          }}
          onDelete={async () => {
            await deleteAssistant(assistantId);
            router.push("/assistants");
          }}
        />
      )}
    </div>
  );
}
