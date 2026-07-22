"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

// Persisted light/dark toggle. A tiny inline script in layout.tsx applies the
// saved choice before first paint (no flash); this component keeps it in sync.
export default function ThemeToggle() {
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
      className="inline-flex items-center gap-2 rounded border border-slate-200 px-2.5 py-1.5 text-[12px] font-medium text-slate-600 hover:border-indigo-300 hover:text-indigo-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-indigo-400"
    >
      {dark ? <Sun size={14} /> : <Moon size={14} />}
      {dark ? "Light" : "Dark"}
    </button>
  );
}
