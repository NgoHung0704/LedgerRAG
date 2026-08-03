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
      // re-pointing that scale to a desaturated ink-blue (fountain-pen ink, not
      // the vivid AI indigo) re-themes the whole app with no component edits.
      colors: {
        indigo: {
          50: "#eef2f5", 100: "#dbe3e9", 200: "#bccbd6", 300: "#94a8b6",
          400: "#688094", 500: "#486174", 600: "#2f4858", 700: "#273b48",
          800: "#1f2f3a", 900: "#17242d", 950: "#0f181f",
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
        // lean on hairline rules, not floating shadows (the SaaS/AI tell)
        card: "0 1px 0 0 rgb(31 47 58 / 0.04), 0 1px 2px 0 rgb(31 47 58 / 0.06)",
      },
    },
  },
  plugins: [typography],
};

export default config;
