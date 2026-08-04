"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  Database,
  FileSearch,
  MessagesSquare,
  ScrollText,
  SlidersHorizontal,
  UserCircle2,
  X,
} from "lucide-react";
import { getMe, type Me } from "@/lib/api";
import ThemeToggle from "@/components/ThemeToggle";
import { IconButton } from "@/components/ui";

const NAV = [
  { href: "/assistants", label: "Assistants", icon: Bot, match: /^\/assistants/, admin: false },
  { href: "/ask", label: "Ask", icon: MessagesSquare, match: /^\/ask/, admin: false },
  { href: "/", label: "Knowledge Bases", icon: Database, match: /^\/($|kb|doc)/, admin: false },
  { href: "/models", label: "Model Providers", icon: SlidersHorizontal, match: /^\/models/, admin: true },
  { href: "/audit", label: "Audit log", icon: ScrollText, match: /^\/audit/, admin: true },
  { href: "/diagnostics", label: "Diagnostics", icon: FileSearch, match: /^\/diagnostics/, admin: false },
];

export default function Sidebar({
  open = false,
  onClose,
}: {
  open?: boolean;
  onClose?: () => void;
}) {
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  // Escape closes the drawer, the same as every other overlay in the app
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose?.();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const nav = NAV.filter((n) => !n.admin || me?.is_admin);

  return (
    <>
      {/* drawer scrim — mobile only, since the rail is always visible above lg */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        id="app-nav"
        // The rail is the frame around the documents, so it is graphite in both
        // themes — light mode changes the table the pages sit on, not the frame.
        className={`fixed inset-y-0 left-0 z-40 flex w-60 shrink-0 flex-col border-r border-rail-line bg-rail text-rail-ink transition-transform duration-200 lg:static lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-start gap-2 px-5 pb-4 pt-5">
          <Link href="/" className="flex min-w-0 items-center gap-2.5">
            <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
              <rect x="2" y="2.5" width="28" height="27" rx="2" fill="none" stroke="currentColor" strokeWidth="1.6" className="text-indigo-400" />
              <line x1="2" y1="10" x2="30" y2="10" stroke="currentColor" strokeWidth="1.2" className="text-indigo-400" />
              <line x1="12" y1="10" x2="12" y2="29.5" stroke="currentColor" strokeWidth="1.2" className="text-indigo-400" />
              <line x1="15.5" y1="16" x2="27" y2="16" stroke="currentColor" strokeWidth="1.6" className="text-amber-500" />
              <line x1="15.5" y1="21" x2="24" y2="21" stroke="currentColor" strokeWidth="1" className="text-indigo-400 opacity-50" />
            </svg>
            <div className="min-w-0">
              <div className="font-serif text-[17px] font-semibold leading-tight tracking-tight text-rail-hi">
                LedgerRAG
              </div>
              <div className="truncate text-[11px] italic leading-tight text-rail-ink/60">
                parse it right, or fail honestly
              </div>
            </div>
          </Link>
          <div className="ml-auto lg:hidden">
            <IconButton
              label="Close navigation"
              onClick={onClose}
              className="!text-rail-ink hover:!bg-white/10 hover:!text-rail-hi"
            >
              <X size={18} />
            </IconButton>
          </div>
        </div>

        <nav aria-label="Main" className="flex-1 space-y-0.5 overflow-y-auto px-3 pt-2">
          {nav.map(({ href, label, icon: Icon, match }) => {
            const active = match.test(pathname);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                // the active page is marked by a verdigris edge, not a filled
                // pill — the rail should read as a margin, not a toolbar
                className={`flex items-center gap-2.5 rounded px-3 py-2.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-white/[0.07] text-rail-hi shadow-[inset_2px_0_0_theme(colors.indigo.400)]"
                    : "text-rail-ink hover:bg-white/[0.05] hover:text-rail-hi"
                }`}
              >
                <Icon size={17} strokeWidth={2} aria-hidden="true" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center justify-between gap-2 border-t border-rail-line px-4 py-3">
          {me ? (
            <div className="flex min-w-0 items-center gap-2">
              <UserCircle2 size={20} className="shrink-0 text-rail-ink/50" aria-hidden="true" />
              <div className="min-w-0">
                <div className="truncate text-[12px] font-medium text-rail-hi">
                  {me.username}
                </div>
                <div className="text-[10px] uppercase tracking-wide text-rail-ink/60">
                  {me.is_admin ? "Admin" : "User"}
                </div>
              </div>
            </div>
          ) : (
            <span />
          )}
          <ThemeToggle />
        </div>
      </aside>
    </>
  );
}
