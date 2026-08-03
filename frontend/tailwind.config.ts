import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  darkMode: "class", // toggled via a `dark` class on <html> (see ThemeToggle)
  theme: {
    extend: {
      // "ledger" identity — humanist serif (Sitka on Windows, Iowan on macOS)
      // for reading, a system sans for dense UI, a ledger mono for figures.
      // All resolve to fonts already present cross-platform (no webfont CDN,
      // which the deploy blocks) so there's no silent fallback.
      fontFamily: {
        sans: ['"Segoe UI"', "-apple-system", "system-ui", "Roboto", "Helvetica", "Arial", "sans-serif"],
        serif: ['"Sitka Text"', '"Iowan Old Style"', '"Palatino Linotype"', "Palatino", "Charter", '"Hoefler Text"', "Georgia", "serif"],
        mono: ['"Cascadia Code"', "Consolas", '"SF Mono"', "ui-monospace", '"Liberation Mono"', "Menlo", "monospace"],
      },
      // The accent ships as Tailwind's `indigo` scale everywhere in the app, so
      // re-pointing that scale re-themes every accent in one edit. It is now
      // verdigris — the patina on aged bronze: archival, institutional, and
      // nowhere near the indigo/violet every AI-built tool reaches for.
      //
      // It carries meaning, not just brand: verdigris is the colour of "checked
      // against the source". Ochre means a parse needs review, oxblood means
      // ingestion failed, and outside those three states nothing is coloured.
      colors: {
        indigo: {
          50: "#eff6f4", 100: "#d9ebe6", 200: "#b4d7ce", 300: "#85bcaf",
          400: "#559c8c", 500: "#33806f", 600: "#1f6b5c", 700: "#1a574b",
          800: "#17453c", 900: "#143931", 950: "#0a211c",
        },
        // the frame — graphite in both themes, see globals.css
        rail: {
          DEFAULT: "rgb(var(--rail) / <alpha-value>)",
          ink: "rgb(var(--rail-ink) / <alpha-value>)",
          hi: "rgb(var(--rail-ink-hi) / <alpha-value>)",
          line: "rgb(var(--rail-line) / <alpha-value>)",
        },
        // Semantic tokens — defined once per theme in globals.css, so a single
        // class (`text-ink-muted`) is correct on paper AND on ink. Written as
        // channel triples so Tailwind's opacity modifiers still work
        // (`bg-canvas/95`).
        canvas: "rgb(var(--canvas) / <alpha-value>)",
        surface: {
          DEFAULT: "rgb(var(--surface) / <alpha-value>)",
          sunken: "rgb(var(--surface-sunken) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--ink) / <alpha-value>)",
          muted: "rgb(var(--ink-muted) / <alpha-value>)",
          subtle: "rgb(var(--ink-subtle) / <alpha-value>)",
          faint: "rgb(var(--ink-faint) / <alpha-value>)",
        },
        line: {
          DEFAULT: "rgb(var(--line) / <alpha-value>)",
          strong: "rgb(var(--line-strong) / <alpha-value>)",
        },
      },
      // documents and ledgers are ruled and near-square, not pill-soft; sharpen
      // the radius scale globally (pills keep `full`).
      borderRadius: {
        sm: "2px", DEFAULT: "3px", md: "4px", lg: "5px", xl: "7px",
        "2xl": "10px", "3xl": "14px",
      },
      boxShadow: {
        // A page has to lift off the table, and the lift needs a different
        // weight on graphite than on grey — so the value lives in a CSS
        // variable that each theme sets (see globals.css).
        card: "var(--shadow-card)",
        lift: "var(--shadow-lift)",
      },
    },
  },
  plugins: [typography],
};

export default config;
