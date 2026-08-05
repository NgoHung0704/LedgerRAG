"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

// Persisted light/dark toggle. A tiny inline script in layout.tsx applies the
// saved choice before first paint (no flash); this component keeps it in sync.
export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      /* private mode / storage disabled — the choice just won't persist */
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Switch to light theme" : "Switch to dark theme"}
      // lives on the rail, so it is styled against navy in both themes
      className={`inline-flex items-center gap-2 rounded-md border border-rail-line text-[12px] font-medium text-rail-ink transition-colors hover:border-indigo-400 hover:text-indigo-300 ${
        compact ? "h-8 w-8 justify-center" : "px-2.5 py-1.5"
      }`}
    >
      {dark ? <Sun size={14} aria-hidden="true" /> : <Moon size={14} aria-hidden="true" />}
      {!compact && (dark ? "Light" : "Dark")}
    </button>
  );
}
