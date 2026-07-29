"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { copyText } from "@/lib/clipboard";

/** Copy some text, with a short confirmation. `tone="light"` for use on a dark
 * background (the question bubble). */
export default function CopyButton({
  text,
  title = "Copy",
  tone = "muted",
  className = "",
}: {
  text: string;
  title?: string;
  tone?: "muted" | "light";
  className?: string;
}) {
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);

  const copy = async () => {
    const ok = await copyText(text);
    setFailed(!ok);
    setDone(ok);
    if (ok) setTimeout(() => setDone(false), 1500);
  };

  const colour =
    tone === "light"
      ? "text-white/60 hover:text-white hover:bg-white/15"
      : "text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 dark:hover:text-slate-200";

  return (
    <button
      type="button"
      onClick={copy}
      title={failed ? "Could not copy — select the text manually" : title}
      aria-label={title}
      className={`rounded-md p-1 transition-colors ${colour} ${className}`}
    >
      {done ? <Check size={13} /> : <Copy size={13} />}
    </button>
  );
}
