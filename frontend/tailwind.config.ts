import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
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
      boxShadow: {
        card: "0 1px 2px 0 rgb(16 24 40 / 0.06), 0 1px 3px 0 rgb(16 24 40 / 0.1)",
      },
    },
  },
  plugins: [typography],
};

export default config;
