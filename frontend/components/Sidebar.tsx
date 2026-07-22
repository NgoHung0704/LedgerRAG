"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Database,
  FileSearch,
  MessagesSquare,
  ScrollText,
  ShieldCheck,
  SlidersHorizontal,
  UserCircle2,
} from "lucide-react";
import { getMe, type Me } from "@/lib/api";

const NAV = [
  { href: "/ask", label: "Ask", icon: MessagesSquare, match: /^\/ask/, admin: false },
  { href: "/", label: "Knowledge Bases", icon: Database, match: /^\/($|kb|doc)/, admin: false },
  { href: "/models", label: "Model Providers", icon: SlidersHorizontal, match: /^\/models/, admin: true },
  { href: "/audit", label: "Audit log", icon: ScrollText, match: /^\/audit/, admin: true },
  { href: "/diagnostics", label: "Diagnostics", icon: FileSearch, match: /^\/diagnostics/, admin: false },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  const nav = NAV.filter((n) => !n.admin || me?.is_admin);

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
      <Link href="/" className="flex items-center gap-2.5 px-5 pb-4 pt-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
          L
        </div>
        <div>
          <div className="text-[15px] font-semibold leading-tight tracking-tight">
            LedgerRAG
          </div>
          <div className="text-[11px] leading-tight text-slate-400">
            self-hosted document Q&A
          </div>
        </div>
      </Link>

      <nav className="flex-1 space-y-0.5 px-3 pt-2">
        {nav.map(({ href, label, icon: Icon, match }) => {
          const active = match.test(pathname);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <Icon size={17} strokeWidth={2} />
              {label}
            </Link>
          );
        })}
      </nav>

      {me && (
        <div className="flex items-center gap-2 border-t border-slate-100 px-4 py-3">
          <UserCircle2 size={20} className="shrink-0 text-slate-400" />
          <div className="min-w-0">
            <div className="truncate text-[12px] font-medium text-slate-700">
              {me.username}
            </div>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">
              {me.is_admin ? "Admin" : "User"}
            </div>
          </div>
        </div>
      )}

      <div className="border-t border-slate-100 px-5 py-4">
        <div className="flex items-start gap-2 text-[11px] leading-snug text-slate-400">
          <ShieldCheck size={14} className="mt-0.5 shrink-0" />
          <span>
            Parse it right, or fail honestly — every table keeps its original
            image.
          </span>
        </div>
      </div>
    </aside>
  );
}
