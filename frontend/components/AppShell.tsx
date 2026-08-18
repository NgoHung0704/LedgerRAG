"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { useT } from "@/components/LocaleProvider";
import Sidebar from "@/components/Sidebar";
import { ConfirmHost } from "@/components/confirm";

/** The frame every page sits in. Above `lg` the sidebar is a fixed rail, as it
 *  always was; below it the rail would eat 240px of a 375px screen, so it
 *  becomes a drawer behind a menu button and the page gets the full width. */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const t = useT();
  const pathname = usePathname();

  // following a link inside the drawer should feel like arriving somewhere,
  // not like being left with the menu still covering the page
  useEffect(() => setNavOpen(false), [pathname]);

  // an embedded page is somebody else's page: no rail, no skip link, none of
  // our chrome around it. The hooks above run first and unconditionally — a
  // hook after this return would change count on the render where the path
  // changes, which React throws on.
  //
  // The more idiomatic Next answer is two route groups with two layouts, but
  // that means moving every existing page into a new directory for the sake of
  // one exception.
  if (pathname?.startsWith("/embed")) return <>{children}</>;

  return (
    <>
      <a href="#main" className="skip-link">
        {t("shell.skip_to_content")}
      </a>

      <div className="flex h-screen overflow-hidden">
        <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />

        <div className="flex min-w-0 flex-1 flex-col">
          {/* the phone's top bar is chrome, so it belongs to the rail */}
          <header className="flex items-center gap-2 border-b border-rail-line bg-rail px-3 py-2 text-rail-ink lg:hidden">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label={t("shell.open_nav")}
              aria-expanded={navOpen}
              aria-controls="app-nav"
              className="inline-flex h-10 w-10 items-center justify-center rounded text-rail-ink transition-colors hover:bg-white/10 hover:text-rail-hi"
            >
              <Menu size={20} />
            </button>
            <span className="font-serif text-[15px] font-semibold tracking-tight text-rail-hi">
              LedgerRAG
            </span>
          </header>

          <main id="main" className="flex-1 overflow-y-auto">
            {/* keyed on the route so arriving somewhere new reads as arriving —
                the page rises into place instead of snapping. `rise` is a no-op
                under prefers-reduced-motion. */}
            <div
              key={pathname}
              className="rise mx-auto max-w-6xl px-4 py-5 sm:px-6 sm:py-6"
            >
              {children}
            </div>
          </main>
        </div>
      </div>

      <ConfirmHost />
    </>
  );
}
