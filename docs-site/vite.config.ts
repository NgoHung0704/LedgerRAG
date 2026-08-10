import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // Pages serves a project site from /<repo>/. Getting this wrong yields a
  // blank page with no error, which is worse than a crash.
  base: "/LedgerRAG/",
  plugins: [react()],
  test: { environment: "jsdom", setupFiles: ["./tests/setup.ts"], globals: true },
});
