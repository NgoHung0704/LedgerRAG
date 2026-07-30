"use client";

import { useEffect, useRef, useState } from "react";
import { Check, CornerDownLeft, Sparkles } from "lucide-react";
import { assistElementEdit, type AssistTurn } from "@/lib/api";
import { Spinner } from "@/components/ui";

type Turn = AssistTurn & { proposal?: string | null };

/** A chat scoped to the content open in the editor: "drop the empty column",
 * "turn these lines into a table", "why is this row wrong?". When it rewrites
 * something it comes back with the complete new version, which is APPLIED BY
 * HAND — the reviewer stays the one who decides, and still saves afterwards. */
export default function EditAssistant({
  elementId,
  format,
  content,
  onApply,
}: {
  elementId: string;
  format: "html" | "text" | "records" | "summary";
  content: string;
  onApply: (next: string) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  const ask = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const instruction = input.trim();
    if (!instruction || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    const asked: Turn[] = [...turns, { role: "user", content: instruction }];
    setTurns(asked);
    try {
      const r = await assistElementEdit(elementId, {
        instruction,
        format,
        content,
        // only the prose travels back: the proposals are long and already applied
        history: turns.map(({ role, content }) => ({ role, content })),
      });
      setTurns([
        ...asked,
        { role: "assistant", content: r.reply, proposal: r.proposal },
      ]);
    } catch (err) {
      setError(String(err));
      setTurns(asked);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-col">
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
        <Sparkles size={11} /> Assistant · {format}
      </div>
      <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900/40">
        <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto p-2.5">
          {turns.length === 0 && (
            <p className="px-1 text-[11px] leading-4 text-slate-400">
              Ask for a change to the {format} on the left — &ldquo;drop the
              empty column&rdquo;, &ldquo;make the first row the header&rdquo;,
              &ldquo;turn these lines into a table&rdquo;. It rearranges what is
              there and never adds figures; you apply the result yourself.
            </p>
          )}
          {turns.map((t, i) =>
            t.role === "user" ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[90%] rounded-lg rounded-br-sm bg-indigo-600 px-2.5 py-1.5 text-[12px] leading-5 text-white">
                  {t.content}
                </div>
              </div>
            ) : (
              <div key={i}>
                <div className="whitespace-pre-wrap rounded-lg rounded-bl-sm bg-slate-100 px-2.5 py-1.5 text-[12px] leading-5 text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                  {t.content}
                </div>
                {t.proposal && (
                  <button
                    type="button"
                    onClick={() => onApply(t.proposal as string)}
                    className="mt-1 inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50 px-2 py-1 text-[11px] font-medium text-indigo-700 hover:bg-indigo-100 dark:border-indigo-900 dark:bg-indigo-950/50 dark:text-indigo-300"
                  >
                    <Check size={11} /> Apply to the {format} pane
                  </button>
                )}
              </div>
            ),
          )}
          {busy && (
            <div className="inline-flex items-center gap-2 text-[11px] text-slate-400">
              <Spinner size={12} /> thinking…
            </div>
          )}
          {error && <p className="text-[11px] text-red-600">{error}</p>}
          <div ref={bottomRef} />
        </div>
        <form
          onSubmit={ask}
          className="flex items-end gap-1.5 border-t border-slate-100 p-2 dark:border-slate-800"
        >
          <textarea
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) ask();
            }}
            placeholder="What should change?"
            disabled={busy}
            className="min-h-0 flex-1 resize-none rounded-md border border-slate-300 px-2 py-1.5 text-[12px] placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-indigo-900/40"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-md bg-indigo-600 p-1.5 text-white hover:bg-indigo-500 disabled:bg-indigo-300"
          >
            <CornerDownLeft size={14} />
          </button>
        </form>
      </div>
    </div>
  );
}
