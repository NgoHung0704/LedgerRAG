"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  BadgeCheck,
  FileText,
  Gauge,
  Search,
  Send,
  Sparkles,
  Table2,
  ThumbsUp,
  ThumbsDown,
} from "lucide-react";
import {
  assistantChatStream,
  chatStream,
  chatMultiStream,
  getElement,
  sendFeedback,
  type Citation,
  type ElementDetail,
  type KB,
  type RoutingInfo,
  type StoredMessage,
  type Verification,
} from "@/lib/api";
import { Spinner } from "@/components/ui";
import CopyButton from "@/components/CopyButton";
import SourceModal from "@/components/SourceModal";
import ChatScopeSelector, { type Scope } from "@/components/ChatScopeSelector";

// what the turn cost, measured client-side: the wait the user actually had.
// searchMs is null for a conversational reply (nothing was retrieved).
type Timing = { searchMs: number | null; genMs: number; chars: number };

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  verification?: Verification | null;
  routing?: RoutingInfo | null;
  messageId?: string;
  feedback?: -1 | 0 | 1;
  error?: boolean;
  timing?: Timing;
};

export default function ChatPanel({
  kbId,
  allKbs = [],
  assistantId,
  conversationId = null,
  initialMessages,
  emptyState,
  onSessionStarted,
}: {
  // no kbId = the standalone Ask page: not anchored to one KB, so the router
  // (or a manual pick) always drives the search — there is no "this KB" scope.
  kbId?: string;
  allKbs?: KB[];
  // assistant mode: the app's own KBs and prompt drive everything, so there is
  // no scope picker — its context is fixed by definition.
  assistantId?: string;
  conversationId?: string | null;
  initialMessages?: StoredMessage[];
  emptyState?: React.ReactNode;
  onSessionStarted?: (sessionId: string) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [openSource, setOpenSource] = useState<Citation | null>(null);
  const [scope, setScope] = useState<Scope>(
    kbId ? { mode: "this" } : { mode: "auto" },
  );
  // the scope picker shows whenever there is a choice: >1 KB when anchored to
  // one, any KB on the standalone Ask page. An assistant has a fixed context.
  const showScope = assistantId
    ? false
    : kbId
      ? allKbs.length > 1
      : allKbs.length >= 1;
  const sessionRef = useRef<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // changing what we search starts a fresh conversation thread
  useEffect(() => {
    if (assistantId) return; // an assistant's thread is driven by conversationId
    sessionRef.current = null;
  }, [scope.mode, kbId, assistantId]);

  // assistant mode: follow the selected conversation (null = a new one) and
  // replay its stored messages, so a reopened thread looks exactly as it did
  useEffect(() => {
    if (!assistantId) return;
    sessionRef.current = conversationId;
    setMessages(
      (initialMessages ?? []).map((m) => ({
        role: m.role,
        content: m.content,
        citations: m.citations,
        verification: m.verification,
        messageId: m.id,
        feedback: m.feedback,
      })),
    );
  }, [assistantId, conversationId, initialMessages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // the composer grows with the question, capped so it never eats the thread
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [question]);

  const rate = async (index: number, next: -1 | 1) => {
    const msg = messages[index];
    if (!msg.messageId) return;
    const value = msg.feedback === next ? 0 : next; // click again to clear
    setMessages((m) => {
      const copy = [...m];
      copy[index] = { ...copy[index], feedback: value };
      return copy;
    });
    try {
      await sendFeedback(msg.messageId, value);
    } catch {
      /* best-effort: feedback is non-critical, keep the optimistic state */
    }
  };

  const ask = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    setBusy(true);
    setMessages((m) => [
      ...m,
      { role: "user", content: q },
      { role: "assistant", content: "" },
    ]);
    const patchLast = (patch: Partial<Message>) =>
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch };
        return copy;
      });

    // an assistant has its own endpoint (its KBs + prompt); otherwise "this KB"
    // uses the scoped endpoint and auto/pinned the multi-KB router
    const isNewThread = sessionRef.current === null;
    const stream = assistantId
      ? assistantChatStream(assistantId, q, sessionRef.current)
      : scope.mode === "this" && kbId
        ? chatStream(kbId, q, sessionRef.current)
        : chatMultiStream(
            q,
            scope.mode === "pinned" ? Array.from(scope.kbIds) : null,
            sessionRef.current,
          );
    // the citations event fires once retrieval + reranking + assembly are done
    // and generation is about to start, so it splits the wait cleanly in two
    const startedAt = performance.now();
    let searchedAt: number | null = null;
    try {
      let answer = "";
      for await (const ev of stream) {
        if (ev.type === "token") {
          answer += ev.content;
          patchLast({ content: answer });
        } else if (ev.type === "citations") {
          searchedAt = performance.now();
          patchLast({ citations: ev.citations });
        } else if (ev.type === "done") {
          sessionRef.current = ev.session_id;
          // a brand-new thread just got saved — let the list pick it up
          if (isNewThread) onSessionStarted?.(ev.session_id);
          const finishedAt = performance.now();
          patchLast({
            verification: ev.verification,
            routing: "routing" in ev ? (ev.routing as RoutingInfo | null) : null,
            messageId: ev.message_id,
            timing: {
              searchMs: searchedAt === null ? null : searchedAt - startedAt,
              genMs: finishedAt - (searchedAt ?? startedAt),
              chars: answer.length,
            },
          });
        } else if (ev.type === "error") {
          patchLast({ content: ev.message, error: true });
        }
      }
    } catch (err) {
      patchLast({ content: String(err), error: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    // dvh, not vh: on a phone `vh` counts the space behind the browser's own
    // toolbars, which pushed the composer off the bottom of the screen. min-h
    // keeps the thread usable when a long KB description eats the header.
    <div className="flex h-[calc(100dvh-17rem)] min-h-[22rem] flex-col rounded-xl border border-line bg-surface shadow-card lg:h-[calc(100dvh-14rem)]">
      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        {messages.length === 0 &&
          (emptyState ?? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <Sparkles size={28} className="mb-3 text-ink-faint" />
              <div className="text-sm font-medium text-ink-muted">
                {kbId
                  ? "Ask anything about the documents in this knowledge base"
                  : "Ask across your knowledge bases"}
              </div>
              <div className="mt-1 max-w-md text-xs leading-5 text-ink-subtle">
                Answers stream with citations. Numbers are quoted exactly as
                printed — when a table couldn't be read reliably, you'll see the
                original image instead of a guess.
              </div>
            </div>
          ))}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="group flex items-start justify-end gap-1">
              <CopyButton
                text={m.content}
                title="Copy the question"
                className="mt-2 opacity-0 transition-opacity group-hover:opacity-100"
              />
              <div className="max-w-[80%] rounded-2xl rounded-br-md bg-indigo-600 px-4 py-2.5 font-serif text-[15px] leading-relaxed text-white">
                {m.content}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="w-full max-w-[92%]">
                <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-subtle">
                  <Sparkles size={12} className="text-indigo-500" /> Assistant
                </div>
                {/* the answer reads like a printed document excerpt, straight on
                    the page — no chat bubble; only errors keep a boxed callout */}
                {m.error ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
                    {m.content}
                  </div>
                ) : m.content ? (
                  <AnswerBody
                    content={m.content}
                    citations={m.citations}
                    onOpen={setOpenSource}
                  />
                ) : busy && i === messages.length - 1 ? (
                  <span className="inline-flex items-center gap-2 text-ink-subtle">
                    <Spinner size={14} /> thinking…
                  </span>
                ) : null}

                {m.routing && <RoutedBadge routing={m.routing} />}

                {m.verification && m.verification.enabled && (
                  <VerificationBadge verification={m.verification} />
                )}

                {m.citations && m.citations.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.citations.map((c) => (
                      <button
                        key={c.index}
                        onClick={() => setOpenSource(c)}
                        title={c.snippet}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                          c.needs_review
                            ? "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-300"
                            : "border-line bg-surface text-ink-muted hover:border-indigo-300 hover:text-indigo-700 dark:hover:border-indigo-500 dark:hover:text-indigo-300"
                        }`}
                      >
                        {c.kind === "table" ? (
                          <Table2 size={12} />
                        ) : (
                          <FileText size={12} />
                        )}
                        [{c.index}] {c.filename} · p.{c.page}
                        {c.needs_review && <AlertTriangle size={12} />}
                      </button>
                    ))}
                  </div>
                )}

                {m.content && !m.error && (
                  <div className="mt-2 flex items-center gap-1">
                    <CopyButton text={m.content} title="Copy the answer" />
                    {m.messageId && (
                      <>
                        <FeedbackButton
                          active={m.feedback === 1}
                          onClick={() => rate(i, 1)}
                          up
                        />
                        <FeedbackButton
                          active={m.feedback === -1}
                          onClick={() => rate(i, -1)}
                        />
                      </>
                    )}
                    {m.timing && <TimingBadge timing={m.timing} />}
                  </div>
                )}
              </div>
            </div>
          ),
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-line p-3">
        {showScope && (
          <div className="mb-2">
            <ChatScopeSelector
              scope={scope}
              onChange={setScope}
              kbId={kbId}
              allKbs={allKbs}
              disabled={busy}
            />
          </div>
        )}
        <form
          onSubmit={ask}
          className="flex items-end gap-2 rounded-xl border border-line-strong bg-surface p-1.5 pl-3 transition-colors focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100 dark:focus-within:ring-indigo-900/40"
        >
          <textarea
            ref={taRef}
            rows={1}
            className="flex-1 resize-none border-0 bg-transparent py-1.5 font-serif text-[15px] leading-relaxed text-ink placeholder:font-sans placeholder:text-sm placeholder:text-ink-subtle focus:outline-none focus:ring-0"
            aria-label="Your question"
            placeholder="Ask your question… (Enter to send, Shift+Enter for a new line)"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask();
              }
            }}
            disabled={busy}
          />
          <button
            type="submit"
            disabled={busy || !question.trim()}
            aria-label="Send question"
            className="relative inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white transition-colors after:absolute after:-inset-1 after:content-[''] hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-indigo-600/40"
          >
            <Send size={15} aria-hidden="true" />
          </button>
        </form>
      </div>

      {openSource && (
        <SourceModal citation={openSource} onClose={() => setOpenSource(null)} />
      )}
    </div>
  );
}

// What the turn cost: the search half (routing + retrieval + reranking, up to
// the citations event) and the generation half. tok/s is the number to watch on
// a self-hosted box — a sudden collapse means the model fell back to the CPU.
function TimingBadge({ timing }: { timing: Timing }) {
  const secs = (ms: number) => `${(ms / 1000).toFixed(1)}s`;
  // same chars/4 estimate the ingestion side uses for sizing
  const tokens = Math.max(1, Math.round(timing.chars / 4));
  const rate = timing.genMs > 0 ? (tokens / (timing.genMs / 1000)).toFixed(0) : null;
  return (
    <span
      className="ml-1 inline-flex items-center gap-1.5 text-[11px] tabular-nums text-ink-subtle"
      title={
        `Search (routing, retrieval, reranking): ${
          timing.searchMs === null ? "not needed" : secs(timing.searchMs)
        }\nGeneration: ${secs(timing.genMs)}\n~${tokens} tokens (estimated)`
      }
    >
      {timing.searchMs !== null && (
        <span className="inline-flex items-center gap-1">
          <Search size={11} /> {secs(timing.searchMs)}
        </span>
      )}
      <span className="inline-flex items-center gap-1">
        <Gauge size={11} /> {secs(timing.genMs)}
        {rate && <span className="text-ink-faint">· {rate} tok/s</span>}
      </span>
    </span>
  );
}

function FeedbackButton({
  active,
  onClick,
  up = false,
}: {
  active: boolean;
  onClick: () => void;
  up?: boolean;
}) {
  const Icon = up ? ThumbsUp : ThumbsDown;
  const activeColor = up ? "text-emerald-600" : "text-red-500";
  return (
    <button
      onClick={onClick}
      title={up ? "Helpful" : "Not helpful"}
      aria-label={up ? "Mark this answer helpful" : "Mark this answer unhelpful"}
      aria-pressed={active}
      className={`relative rounded-md p-1.5 transition-colors after:absolute after:-inset-1 after:content-[''] hover:bg-surface-sunken ${
        active ? activeColor : "text-ink-subtle hover:text-ink-muted"
      }`}
    >
      <Icon size={13} fill={active ? "currentColor" : "none"} aria-hidden="true" />
    </button>
  );
}

// Split an answer into prose runs and GFM-table blocks, in order. A markdown
// table is a run of pipe lines whose first two include a `---` delimiter row.
function splitAnswerSegments(
  content: string,
): { type: "prose" | "table"; text: string }[] {
  const lines = content.split("\n");
  const isPipe = (l: string) => /^\s*\|/.test(l);
  const isDelim = (l: string) => /-/.test(l) && /^\s*\|?[\s:|-]+$/.test(l);
  const out: { type: "prose" | "table"; text: string }[] = [];
  let i = 0;
  while (i < lines.length) {
    if (isPipe(lines[i])) {
      let j = i;
      while (j < lines.length && isPipe(lines[j])) j++;
      const block = lines.slice(i, j);
      const isTable = block.length >= 2 && block.slice(0, 2).some(isDelim);
      out.push({ type: isTable ? "table" : "prose", text: block.join("\n") });
      i = j;
    } else {
      let j = i;
      while (j < lines.length && !isPipe(lines[j])) j++;
      out.push({ type: "prose", text: lines.slice(i, j).join("\n") });
      i = j;
    }
  }
  return out;
}

// A table the model typed as markdown is a lossy re-keying of a table we
// already parsed cleanly (merged cells, in-cell line breaks). So when the
// answer paints a table AND cites a table source, show the authoritative
// stored HTML in its place; the prose and its citations stay untouched.
function AnswerBody({
  content,
  citations,
  onOpen,
}: {
  content: string;
  citations?: Citation[];
  onOpen: (c: Citation) => void;
}) {
  const segments = splitAnswerSegments(content);
  const tableCitations = (citations ?? []).filter((c) => c.kind === "table");
  let t = 0;
  return (
    <div className="space-y-1">
      {segments.map((seg, i) => {
        if (seg.type === "table") {
          const cite = tableCitations[t++];
          if (cite)
            return (
              <SourceTable
                key={i}
                citation={cite}
                fallback={seg.text}
                citations={citations}
                onOpen={onOpen}
              />
            );
        }
        if (!seg.text.trim()) return null;
        return (
          <MarkdownProse
            key={i}
            content={seg.text}
            citations={citations}
            onOpen={onOpen}
          />
        );
      })}
    </div>
  );
}

// Prose (or a fallback markdown table). Inline citation markers ([1], [2][3])
// become clickable receipts that open the exact source — provenance made
// tactile: the answer's numbers trace back to the table they came from.
function MarkdownProse({
  content,
  citations,
  onOpen,
}: {
  content: string;
  citations?: Citation[];
  onOpen: (c: Citation) => void;
}) {
  // [1] -> [[1]](#cite-1) so markdown renders a link we can intercept
  const linked = content.replace(/\[(\d+)\]/g, "[[$1]](#cite-$1)");
  return (
    // dark:prose-invert is load-bearing: without it the typography plugin pins
    // body text to a dark slate that all but disappears on the dark bubble
    <div className="chat-md prose prose-sm max-w-none prose-p:my-1.5 prose-headings:my-2 dark:prose-invert">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children }) {
            const m = /^#cite-(\d+)$/.exec(href ?? "");
            if (!m) return <a href={href}>{children}</a>;
            const c = citations?.find((x) => x.index === Number(m[1]));
            if (!c) return <sup className="text-ink-subtle">{children}</sup>;
            return (
              <button
                type="button"
                onClick={() => onOpen(c)}
                title={`${c.filename} · p.${c.page}${c.needs_review ? " · needs review" : ""}`}
                className={`mx-0.5 align-super text-[11px] font-semibold no-underline ${
                  c.needs_review
                    ? "text-amber-700 hover:text-amber-800 dark:text-amber-400"
                    : "text-indigo-700 hover:text-indigo-900 dark:text-indigo-400"
                } hover:underline`}
              >
                {children}
              </button>
            );
          },
        }}
      >
        {linked}
      </ReactMarkdown>
    </div>
  );
}

// The parsed table rendered from its authoritative stored HTML (rowspans and
// all), as in the document viewer — falls back to the model's markdown if the
// element can't be fetched.
function SourceTable({
  citation,
  fallback,
  citations,
  onOpen,
}: {
  citation: Citation;
  fallback: string;
  citations?: Citation[];
  onOpen: (c: Citation) => void;
}) {
  const [detail, setDetail] = useState<ElementDetail | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    getElement(citation.element_id)
      .then((d) => alive && setDetail(d))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [citation.element_id]);

  if (!failed && !detail)
    return (
      <div className="my-2 flex items-center gap-2 text-xs text-ink-subtle">
        <Spinner size={12} label="Loading the original table" /> loading the
        original table…
      </div>
    );

  const html = detail?.table?.html;
  if (failed || !html)
    return (
      <MarkdownProse content={fallback} citations={citations} onOpen={onOpen} />
    );

  return (
    <figure className="my-2">
      <div
        className="doc-table max-h-[60vh] overflow-auto rounded-lg border border-line p-2"
        dangerouslySetInnerHTML={{ __html: html }}
      />
      <figcaption className="mt-1 flex flex-wrap items-center gap-1.5 font-sans text-[11px] text-ink-subtle">
        <button
          type="button"
          onClick={() => onOpen(citation)}
          className="inline-flex items-center gap-1 hover:text-indigo-600 dark:hover:text-indigo-300"
        >
          <Table2 size={11} aria-hidden="true" /> {citation.filename} · p.
          {citation.page} — see the original
        </button>
        {citation.needs_review && (
          <span className="text-amber-700 dark:text-amber-400">
            · parse needs review
          </span>
        )}
      </figcaption>
    </figure>
  );
}

function RoutedBadge({ routing }: { routing: RoutingInfo }) {
  // nothing to show when the search wasn't a routing decision
  if (routing.mode === "single" || routing.mode === "trivial") return null;
  const label =
    routing.mode === "pinned"
      ? "Searched the knowledge bases you chose"
      : routing.mode === "fallback_all"
        ? `Unsure — searched all ${routing.kb_ids.length} knowledge bases`
        : routing.names && routing.names.length > 0
          ? `Routed to: ${routing.names.join(", ")}`
          : `Routed to ${routing.kb_ids.length} knowledge base(s)`;
  const warn = routing.mode === "fallback_all";
  return (
    <div
      className={`mt-2 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ${
        warn
          ? "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-800/60"
          : "bg-sky-50 text-sky-700 ring-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:ring-sky-800/60"
      }`}
    >
      <Sparkles size={11} /> {label}
    </div>
  );
}

function VerificationBadge({ verification }: { verification: Verification }) {
  const verified = verification.numbers.filter(
    (n) => n.status !== "unverified",
  ).length;
  const total = verification.numbers.length;
  if (total === 0) return null;

  if (verification.status === "ok") {
    return (
      <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-800/60">
        <BadgeCheck size={12} />
        {total} number{total === 1 ? "" : "s"} checked against sources
      </div>
    );
  }
  return (
    <div className="mt-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] text-amber-800 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-200">
      <div className="flex items-center gap-1.5 font-medium">
        <AlertTriangle size={13} />
        {verification.unverified.length} number
        {verification.unverified.length === 1 ? "" : "s"} could not be matched to
        a source
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        {verification.unverified.map((raw, i) => (
          <code
            key={i}
            className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[11px]"
          >
            {raw}
          </code>
        ))}
      </div>
      <div className="mt-1 text-[11px] text-amber-700">
        {verified}/{total} verified. Check the cited sources for the rest.
      </div>
    </div>
  );
}
