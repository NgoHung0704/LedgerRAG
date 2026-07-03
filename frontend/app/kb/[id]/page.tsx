"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  chatStream,
  getDocs,
  getKb,
  pageImageUrl,
  uploadDoc,
  type Citation,
  type Doc,
  type KB,
} from "@/lib/api";

const STATUS_STYLE: Record<Doc["status"], string> = {
  queued: "bg-slate-100 text-slate-600",
  parsing: "bg-amber-100 text-amber-700",
  indexing: "bg-blue-100 text-blue-700",
  done: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  error?: boolean;
};

export default function KBPage({ params }: { params: { id: string } }) {
  const kbId = params.id;
  const [kb, setKb] = useState<KB | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const refreshDocs = useCallback(
    () => getDocs(kbId).then(setDocs).catch(() => {}),
    [kbId],
  );

  useEffect(() => {
    getKb(kbId).then(setKb).catch(() => {});
    refreshDocs();
  }, [kbId, refreshDocs]);

  // poll while any document is still being processed
  const processing = docs.some((d) => !["done", "failed"].includes(d.status));
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(refreshDocs, 2000);
    return () => clearInterval(t);
  }, [processing, refreshDocs]);

  const onUpload = async (files: FileList | null) => {
    if (!files) return;
    setUploadError(null);
    for (const file of Array.from(files)) {
      try {
        await uploadDoc(kbId, file);
      } catch (e) {
        setUploadError(String(e));
      }
    }
    refreshDocs();
  };

  // ---- chat ----
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
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
    <div className="grid gap-6 lg:grid-cols-[2fr,3fr]">
      {/* documents column */}
      <section className="space-y-4">
        <div>
          <h1 className="text-xl font-semibold">{kb?.name ?? "…"}</h1>
          {kb?.description && (
            <p className="text-sm text-slate-500">{kb.description}</p>
          )}
        </div>

        <label className="block cursor-pointer rounded-lg border-2 border-dashed bg-white p-6 text-center text-sm text-slate-500 hover:border-slate-400">
          Click to upload PDF documents
          <input
            type="file"
            accept="application/pdf"
            multiple
            className="hidden"
            onChange={(e) => onUpload(e.target.files)}
          />
        </label>
        {uploadError && <p className="text-sm text-red-600">{uploadError}</p>}

        <ul className="space-y-2">
          {docs.map((d) => (
            <li
              key={d.id}
              className="rounded-lg border bg-white px-3 py-2 text-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">{d.filename}</span>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${STATUS_STYLE[d.status]}`}
                >
                  {d.status}
                  {d.page_count != null && d.status === "done"
                    ? ` · ${d.page_count} p.`
                    : ""}
                </span>
              </div>
              {d.status === "failed" && d.error && (
                <p className="mt-1 text-xs text-red-600">{d.error}</p>
              )}
            </li>
          ))}
        </ul>
      </section>

      {/* chat column */}
      <section className="flex h-[75vh] flex-col rounded-lg border bg-white">
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 && (
            <p className="text-sm text-slate-400">
              Ask a question about the documents in this knowledge base.
            </p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : ""}>
              <div
                className={`inline-block max-w-[90%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
                  m.role === "user"
                    ? "bg-slate-900 text-white"
                    : m.error
                      ? "bg-red-50 text-red-700"
                      : "bg-slate-100"
                }`}
              >
                {m.content || (busy && i === messages.length - 1 ? "…" : "")}
              </div>
              {m.citations && m.citations.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {m.citations.map((c) => (
                    <a
                      key={c.index}
                      href={pageImageUrl(c.doc_id, c.page)}
                      target="_blank"
                      rel="noreferrer"
                      title={c.snippet}
                      className={`rounded-full border px-2 py-0.5 text-xs hover:bg-slate-50 ${
                        c.needs_review
                          ? "border-amber-400 text-amber-700"
                          : "text-slate-600"
                      }`}
                    >
                      [{c.index}] {c.filename} · p.{c.page}
                      {c.needs_review ? " ⚠" : ""}
                    </a>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        <form onSubmit={ask} className="flex gap-2 border-t p-3">
          <input
            className="flex-1 rounded border px-3 py-2 text-sm"
            placeholder="Posez votre question… / Ask your question…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={busy}
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </section>
    </div>
  );
}
