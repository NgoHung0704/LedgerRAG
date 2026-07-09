"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  BadgeCheck,
  FileText,
  Send,
  Sparkles,
  Table2,
} from "lucide-react";
import { chatStream, type Citation, type Verification } from "@/lib/api";
import { Spinner } from "@/components/ui";
import SourceModal from "@/components/SourceModal";

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  verification?: Verification | null;
  error?: boolean;
};

export default function ChatPanel({ kbId }: { kbId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [openSource, setOpenSource] = useState<Citation | null>(null);
  const sessionRef = useRef<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
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
    try {
      let answer = "";
      for await (const ev of chatStream(kbId, q, sessionRef.current)) {
        if (ev.type === "token") {
          answer += ev.content;
          patchLast({ content: answer });
        } else if (ev.type === "citations") {
          patchLast({ citations: ev.citations });
        } else if (ev.type === "done") {
          sessionRef.current = ev.session_id;
          patchLast({ verification: ev.verification });
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
    <div className="flex h-[calc(100vh-14rem)] flex-col rounded-xl border border-slate-200 bg-white shadow-card">
      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <Sparkles size={28} className="mb-3 text-slate-300" />
            <div className="text-sm font-medium text-slate-600">
              Ask anything about the documents in this knowledge base
            </div>
            <div className="mt-1 max-w-md text-xs leading-5 text-slate-400">
              Answers stream with citations. Numbers are quoted exactly as
              printed — when a table couldn't be read reliably, you'll see the
              original image instead of a guess.
            </div>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-br-md bg-indigo-600 px-4 py-2.5 text-sm text-white">
                {m.content}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="max-w-[88%]">
                <div
                  className={`rounded-2xl rounded-bl-md border px-4 py-3 text-sm leading-6 ${
                    m.error
                      ? "border-red-200 bg-red-50 text-red-700"
                      : "border-slate-200 bg-slate-50 text-slate-800"
                  }`}
                >
                  {m.content ? (
                    <div className="chat-md prose prose-sm max-w-none prose-p:my-1.5 prose-headings:my-2">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {m.content}
                      </ReactMarkdown>
                    </div>
                  ) : busy && i === messages.length - 1 ? (
                    <span className="inline-flex items-center gap-2 text-slate-400">
                      <Spinner size={14} /> thinking…
                    </span>
                  ) : null}
                </div>

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
                            ? "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100"
                            : "border-slate-200 bg-white text-slate-600 hover:border-indigo-300 hover:text-indigo-700"
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
              </div>
            </div>
          ),
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={ask} className="flex gap-2 border-t border-slate-100 p-3">
        <input
          className="flex-1 rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          placeholder="Posez votre question… / Ask your question…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-indigo-300"
        >
          <Send size={15} />
        </button>
      </form>

      {openSource && (
        <SourceModal citation={openSource} onClose={() => setOpenSource(null)} />
      )}
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
      <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
        <BadgeCheck size={12} />
        {total} number{total === 1 ? "" : "s"} checked against sources
      </div>
    );
  }
  return (
    <div className="mt-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
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
