"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  Database,
  FileSearch,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  SlidersHorizontal,
  UserCircle2,
  X,
  type LucideIcon,
} from "lucide-react";
import { getMe, type Me } from "@/lib/api";
import ThemeToggle from "@/components/ThemeToggle";
import { useT } from "@/components/LocaleProvider";
import LocaleToggle from "@/components/LocaleToggle";
import { IconButton } from "@/components/ui";
import type { MessageKey } from "@/messages/en";

const NAV: { href: string; labelKey: MessageKey; icon: LucideIcon;
             match: RegExp; admin: boolean }[] = [
  { href: "/assistants", labelKey: "nav.assistants", icon: Bot, match: /^\/assistants/, admin: false },
  { href: "/ask", labelKey: "nav.ask", icon: MessagesSquare, match: /^\/ask/, admin: false },
  { href: "/", labelKey: "nav.knowledge_bases", icon: Database, match: /^\/($|kb|doc)/, admin: false },
  { href: "/models", labelKey: "nav.model_providers", icon: SlidersHorizontal, match: /^\/models/, admin: true },
  { href: "/audit", labelKey: "nav.audit_log", icon: ScrollText, match: /^\/audit/, admin: true },
  { href: "/diagnostics", labelKey: "nav.diagnostics", icon: FileSearch, match: /^\/diagnostics/, admin: false },
];

const STORE = "rail-collapsed";

export default function Sidebar({
  open = false,
  onClose,
}: {
  open?: boolean;
  onClose?: () => void;
}) {
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const navRef = useRef<HTMLElement>(null);
  const [marker, setMarker] = useState<{ top: number; height: number } | null>(null);

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  // the rail remembers how you left it
  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(STORE) === "1");
    } catch {
      /* storage disabled — the rail just starts expanded every time */
    }
  }, []);
  const toggle = () =>
    setCollapsed((v) => {
      try {
        localStorage.setItem(STORE, v ? "0" : "1");
      } catch {
        /* ignore */
      }
      return !v;
    });

  // Escape closes the drawer, the same as every other overlay in the app
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose?.();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // The active marker is one element that MOVES between items rather than a
  // border that blinks on and off — the eye follows it and keeps its place.
  const place = useCallback(() => {
    const el = navRef.current?.querySelector<HTMLElement>("[data-active='true']");
    setMarker(el ? { top: el.offsetTop, height: el.offsetHeight } : null);
  }, []);
  useLayoutEffect(place, [place, pathname, collapsed, me]);
  useEffect(() => {
    addEventListener("resize", place);
    return () => removeEventListener("resize", place);
  }, [place]);

  const t = useT();
  const nav = NAV.filter((n) => !n.admin || me?.is_admin);

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/50 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        id="app-nav"
        data-collapsed={collapsed ? "" : undefined}
        className={`fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col border-r border-rail-line bg-rail text-rail-ink transition-[transform,width] duration-300 lg:static lg:translate-x-0 ${
          collapsed ? "w-[68px]" : "w-60"
        } ${open ? "translate-x-0" : "-translate-x-full"}`}
        style={{ transitionTimingFunction: "cubic-bezier(.2,.9,.25,1)" }}
      >
        <div className="flex items-start gap-2 px-4 pb-4 pt-4">
          <Link
            href="/"
            className="emblem group flex min-w-0 items-center gap-2.5 rounded"
            aria-label="LedgerRAG — home"
          >
            <Emblem />
            {!collapsed && (
              <div className="min-w-0">
                <div className="font-display text-[16px] font-bold leading-tight tracking-[0.01em] text-rail-hi">
                  LedgerRAG
                </div>
                <div className="truncate text-[10.5px] leading-tight text-rail-ink/55">
                  parse it right, or fail honestly
                </div>
              </div>
            )}
          </Link>
          {!collapsed && (
            <div className="ml-auto lg:hidden">
              <IconButton
                label="Close navigation"
                onClick={onClose}
                className="!text-rail-ink hover:!bg-white/10 hover:!text-rail-hi"
              >
                <X size={18} />
              </IconButton>
            </div>
          )}
        </div>

        <nav
          ref={navRef}
          aria-label="Main"
          className="relative flex-1 space-y-0.5 overflow-y-auto px-2.5 pt-1"
        >
          {marker && (
            <span
              aria-hidden="true"
              className="absolute left-0 w-[3px] rounded-r bg-indigo-400 transition-[transform,height] duration-300"
              style={{
                height: marker.height,
                transform: `translateY(${marker.top}px)`,
                transitionTimingFunction: "cubic-bezier(.2,.9,.25,1)",
              }}
            />
          )}
          {nav.map(({ href, labelKey, icon: Icon, match }) => {
            const active = match.test(pathname);
            return (
              <Link
                key={href}
                href={href}
                data-active={active}
                aria-current={active ? "page" : undefined}
                title={collapsed ? t(labelKey) : undefined}
                className={`flex items-center gap-2.5 rounded-md px-3 py-2.5 text-[13.5px] font-medium transition-colors ${
                  collapsed ? "justify-center px-0" : ""
                } ${
                  active
                    ? "bg-white/[0.08] text-rail-hi"
                    : "text-rail-ink hover:bg-white/[0.05] hover:text-rail-hi"
                }`}
              >
                <Icon size={17} strokeWidth={2} className="shrink-0" aria-hidden="true" />
                {!collapsed && <span className="truncate">{t(labelKey)}</span>}
                {collapsed && <span className="sr-only">{t(labelKey)}</span>}
              </Link>
            );
          })}
        </nav>

        <div
          className={`flex items-center gap-2 border-t border-rail-line px-3 py-3 ${
            collapsed ? "flex-col" : "justify-between"
          }`}
        >
          {me && !collapsed && (
            <div className="flex min-w-0 items-center gap-2">
              <UserCircle2 size={20} className="shrink-0 text-rail-ink/50" aria-hidden="true" />
              <div className="min-w-0">
                <div className="truncate text-[12px] font-medium text-rail-hi">
                  {me.username}
                </div>
                <div className="text-[10px] uppercase tracking-wide text-rail-ink/55">
                  {me.is_admin ? "Admin" : "User"}
                </div>
              </div>
            </div>
          )}
          {me && collapsed && (
            <UserCircle2
              size={20}
              className="text-rail-ink/50"
              aria-label={`Signed in as ${me.username}`}
            />
          )}
          <LocaleToggle compact={collapsed} />
          <ThemeToggle compact={collapsed} />
        </div>

        <div className="hidden border-t border-rail-line p-2 lg:block">
          <button
            type="button"
            onClick={toggle}
            aria-label={collapsed ? "Expand the navigation rail" : "Collapse the navigation rail"}
            aria-expanded={!collapsed}
            aria-controls="app-nav"
            title={collapsed ? "Expand" : "Collapse"}
            className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-[12px] font-medium text-rail-ink transition-colors hover:bg-white/[0.06] hover:text-rail-hi ${
              collapsed ? "justify-center px-0" : ""
            }`}
          >
            {collapsed ? (
              <PanelLeftOpen size={16} aria-hidden="true" />
            ) : (
              <PanelLeftClose size={16} aria-hidden="true" />
            )}
            {!collapsed && "Collapse"}
          </button>
        </div>
      </aside>
    </>
  );
}

/** The mark is the product doing its job: a page of ruled lines with a scan
 *  crossing it, forever, faster when you point at it. */
function Emblem() {
  return (
    <svg
      width="30"
      height="30"
      viewBox="0 0 32 32"
      aria-hidden="true"
      className="shrink-0 overflow-hidden"
    >
      <rect
        x="4"
        y="2.5"
        width="24"
        height="27"
        rx="4"
        className="fill-indigo-600/15 stroke-indigo-400"
        strokeWidth="1.5"
      />
      <g className="stroke-indigo-300" strokeWidth="1.6" strokeLinecap="round">
        <line x1="9" y1="10" x2="23" y2="10" className="emblem-rule" opacity="0.75" />
        <line x1="9" y1="15" x2="20" y2="15" className="emblem-rule" opacity="0.55" style={{ transitionDelay: "40ms" }} />
        <line x1="9" y1="20" x2="22" y2="20" className="emblem-rule" opacity="0.55" style={{ transitionDelay: "80ms" }} />
        <line x1="9" y1="25" x2="17" y2="25" className="emblem-rule" opacity="0.35" style={{ transitionDelay: "120ms" }} />
      </g>
      {/* the scan */}
      <g className="emblem-scan">
        <rect x="4" y="6" width="24" height="1.5" className="fill-indigo-400" opacity="0.9" />
        <rect x="4" y="7.5" width="24" height="3" className="fill-indigo-400" opacity="0.18" />
      </g>
    </svg>
  );
}
