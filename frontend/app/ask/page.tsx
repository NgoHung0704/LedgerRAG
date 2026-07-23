"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { MessagesSquare, Sparkles, Database } from "lucide-react";
import { getKbs, type KB } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";

// Standalone chat, not anchored to one KB: ask a question and the router picks
// the right knowledge base(s), or tick a group yourself. This is the answer to
// "how do I chat across several KBs" — it lives above any single KB.
export default function AskPage() {
  const [kbs, setKbs] = useState<KB[] | null>(null);

  useEffect(() => {
    getKbs()
      .then(setKbs)
      .catch(() => setKbs([]));
  }, []);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <MessagesSquare size={20} /> Ask
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
          Ask across your knowledge bases. The assistant auto-routes to the
          relevant one(s) by their descriptions — or use{" "}
          <span className="font-medium text-slate-600 dark:text-slate-300">Search in</span> to pick
          a specific group.
        </p>
      </div>

      {kbs && kbs.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 text-center dark:border-slate-700">
          <Database size={26} className="mb-2 text-slate-300 dark:text-slate-600" />
          <div className="text-sm font-medium text-slate-600 dark:text-slate-300">
            No knowledge bases yet
          </div>
          <p className="mt-1 max-w-xs text-xs text-slate-400 dark:text-slate-500">
            Create one and upload documents, then come back here to ask across
            them.
          </p>
          <Link
            href="/"
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
          >
            <Sparkles size={13} /> Go to Knowledge Bases
          </Link>
        </div>
      ) : (
        <div className="min-h-0 flex-1">
          <ChatPanel allKbs={kbs ?? []} />
        </div>
      )}
    </div>
  );
}
