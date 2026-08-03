"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import { ConfirmHost } from "@/components/confirm";

/** The frame every page sits in. Above `lg` the sidebar is a fixed rail, as it
 *  always was; below it the rail would eat 240px of a 375px screen, so it
 *  becomes a drawer behind a menu button and the page gets the full width. */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const pathname = usePathname();

  // following a link inside the drawer should feel like arriving somewhere,
  // not like being left with the menu still covering the page
  useEffect(() => setNavOpen(false), [pathname]);

  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <div className="flex h-screen overflow-hidden">
        <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center gap-2 border-b border-line bg-surface px-3 py-2 lg:hidden">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label="Open navigation"
              aria-expanded={navOpen}
              aria-controls="app-nav"
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink"
            >
              <Menu size={20} />
            </button>
            <span className="font-serif text-[15px] font-semibold tracking-tight">
              LedgerRAG
            </span>
          </header>

          <main id="main" className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6 sm:py-6">
              {children}
            </div>
          </main>
        </div>
      </div>

      <ConfirmHost />
    </>
  );
}
