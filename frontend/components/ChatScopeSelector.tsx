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
        aria-expanded={open}
        aria-haspopup="listbox"
        className="inline-flex min-h-8 items-center gap-1.5 rounded-lg bg-indigo-50 px-2.5 py-1 text-[12px] font-medium text-indigo-700 ring-1 ring-inset ring-indigo-200/80 transition-[background-color,box-shadow,transform] duration-150 hover:bg-indigo-100 hover:ring-indigo-300 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 dark:bg-indigo-950/60 dark:text-indigo-300 dark:ring-indigo-800/70 dark:hover:bg-indigo-900/60"
      >
        <Sparkles size={13} aria-hidden="true" />
        <span className="opacity-70">Search in:</span> {summary}
        <ChevronDown
          size={13}
          aria-hidden="true"
          className={`opacity-70 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="pop absolute bottom-full z-20 mb-1.5 w-80 origin-bottom-left rounded-xl border border-line bg-surface p-1.5 shadow-lift">
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
            <div className="mt-1 max-h-52 overflow-y-auto border-t border-line pt-1.5">
              {allKbs.map((kb) => {
                const on = scope.kbIds.has(kb.id);
                return (
                  <button
                    key={kb.id}
                    type="button"
                    onClick={() => togglePinned(kb.id)}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[12px] hover:bg-surface-sunken"
                  >
                    <span
                      className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                        on
                          ? "border-indigo-500 bg-indigo-500 text-white"
                          : "border-line-strong"
                      }`}
                    >
                      {on && <Check size={11} />}
                    </span>
                    <span className="truncate text-ink">{kb.name}</span>
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
        active ? "bg-indigo-50 dark:bg-indigo-950/50" : "hover:bg-surface-sunken"
      }`}
    >
      <span className={active ? "text-indigo-600 dark:text-indigo-300" : "text-ink-subtle"}>
        {icon}
      </span>
      <span className="min-w-0">
        <span
          className={`block text-[12.5px] font-medium ${
            active ? "text-indigo-700 dark:text-indigo-300" : "text-ink"
          }`}
        >
          {title}
        </span>
        {subtitle && (
          <span className="block truncate text-[11px] text-ink-subtle">
            {subtitle}
          </span>
        )}
      </span>
      {active && <Check size={14} className="ml-auto mt-0.5 text-indigo-600" />}
    </button>
  );
}
