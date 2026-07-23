"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Sparkles, Database, ListChecks } from "lucide-react";
import type { KB } from "@/lib/api";

// "this": only the current KB (scoped endpoint). "auto": the router picks.
// "pinned": a manual set the user chose (router override).
export type Scope =
  | { mode: "this" }
  | { mode: "auto" }
  | { mode: "pinned"; kbIds: Set<string> };

export default function ChatScopeSelector({
  scope,
  onChange,
  kbId,
  allKbs,
  disabled,
}: {
  scope: Scope;
  onChange: (s: Scope) => void;
  kbId?: string;
  allKbs: KB[];
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const thisKb = allKbs.find((k) => k.id === kbId);
  const summary =
    scope.mode === "this"
      ? `This KB · ${thisKb?.name ?? "…"}`
      : scope.mode === "auto"
        ? "Auto — let the assistant choose"
        : `${scope.kbIds.size} knowledge base${scope.kbIds.size === 1 ? "" : "s"} chosen`;

  const togglePinned = (id: string) => {
    const set =
      scope.mode === "pinned" ? new Set(scope.kbIds) : new Set<string>();
    if (set.has(id)) set.delete(id);
    else set.add(id);
    onChange({ mode: "pinned", kbIds: set });
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-slate-600 hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-indigo-500"
      >
        <Sparkles size={13} className="text-indigo-500" />
        <span className="text-slate-400 dark:text-slate-500">Search in:</span> {summary}
        <ChevronDown size={13} className="text-slate-400" />
      </button>

      {open && (
        <div className="absolute bottom-full z-20 mb-1.5 w-80 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg dark:border-slate-700 dark:bg-[#1b222a]">
          {kbId && (
            <Option
              icon={<Database size={15} />}
              title="This knowledge base"
              subtitle={thisKb?.name}
              active={scope.mode === "this"}
              onClick={() => {
                onChange({ mode: "this" });
                setOpen(false);
              }}
            />
          )}
          <Option
            icon={<Sparkles size={15} />}
            title="Auto-route"
            subtitle="Let the assistant pick the right KB(s) by their descriptions"
            active={scope.mode === "auto"}
            onClick={() => {
              onChange({ mode: "auto" });
              setOpen(false);
            }}
          />
          <Option
            icon={<ListChecks size={15} />}
            title="Choose specific knowledge bases"
            subtitle="Search exactly the ones you tick"
            active={scope.mode === "pinned"}
            onClick={() =>
              onChange({
                mode: "pinned",
                kbIds:
                  scope.mode === "pinned"
                    ? scope.kbIds
                    : new Set(kbId ? [kbId] : []),
              })
            }
          />
          {scope.mode === "pinned" && (
            <div className="mt-1 max-h-52 overflow-y-auto border-t border-slate-100 pt-1.5 dark:border-slate-700">
              {allKbs.map((kb) => {
                const on = scope.kbIds.has(kb.id);
                return (
                  <button
                    key={kb.id}
                    type="button"
                    onClick={() => togglePinned(kb.id)}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[12px] hover:bg-slate-50 dark:hover:bg-slate-800"
                  >
                    <span
                      className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                        on
                          ? "border-indigo-500 bg-indigo-500 text-white"
                          : "border-slate-300 dark:border-slate-600"
                      }`}
                    >
                      {on && <Check size={11} />}
                    </span>
                    <span className="truncate text-slate-700 dark:text-slate-300">{kb.name}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Option({
  icon,
  title,
  subtitle,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left ${
        active ? "bg-indigo-50 dark:bg-indigo-950/50" : "hover:bg-slate-50 dark:hover:bg-slate-800"
      }`}
    >
      <span className={active ? "text-indigo-600 dark:text-indigo-300" : "text-slate-400"}>
        {icon}
      </span>
      <span className="min-w-0">
        <span
          className={`block text-[12.5px] font-medium ${
            active ? "text-indigo-700 dark:text-indigo-300" : "text-slate-700 dark:text-slate-200"
          }`}
        >
          {title}
        </span>
        {subtitle && (
          <span className="block truncate text-[11px] text-slate-400 dark:text-slate-500">
            {subtitle}
          </span>
        )}
      </span>
      {active && <Check size={14} className="ml-auto mt-0.5 text-indigo-600" />}
    </button>
  );
}
