"use client";

import { useT } from "@/components/LocaleProvider";
import { useEffect, useState } from "react";
import Link from "next/link";
import { MessagesSquare, Sparkles, Database } from "lucide-react";
import { getKbs, type KB } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";

// Standalone chat, not anchored to one KB: ask a question and the router picks
// the right knowledge base(s), or tick a group yourself. This is the answer to
// "how do I chat across several KBs" — it lives above any single KB.
export default function AskPage() {
  const t = useT();
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
          <MessagesSquare size={20} /> {t("ask.title")}
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-muted">
          {t("ask.lede")}{" "}
          <span className="font-medium text-ink-muted">{t("scope.search_in")}</span>{" "}
          {t("ask.lede_tail")}
        </p>
      </div>

      {kbs && kbs.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-line-strong text-center">
          <Database size={26} className="mb-2 text-ink-faint" />
          <div className="text-sm font-medium text-ink-muted">
            {t("ask.no_kbs")}
          </div>
          <p className="mt-1 max-w-xs text-xs text-ink-subtle">
            {t("ask.no_kbs_body")}
          </p>
          <Link
            href="/"
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
          >
            <Sparkles size={13} /> {t("ask.go_to_kbs")}
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
