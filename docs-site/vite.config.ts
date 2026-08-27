import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Where the site will be served from. GitHub Pages serves a project site under
// /<repo>/; a Gitea host behind Nginx, or Cloudflare Pages, serves it at "/".
// Getting this wrong yields a blank page with no error, which is worse than a
// crash — so it is one build-time variable rather than a value edited in place.
//
//   SITE_BASE=/ npx vite build          # a domain or subdomain root
//   npx vite build                      # GitHub Pages, /LedgerRAG/
const base = process.env.SITE_BASE || "/LedgerRAG/";

// Where the citations point. A company Gitea, say:
//   SITE_FORGE=https://git.example.com/team/LedgerRAG/src/branch/main
const forge = process.env.SITE_FORGE
  || "https://github.com/NgoHung0704/LedgerRAG/blob/main";

export default defineConfig({
  base,
  define: { __FORGE__: JSON.stringify(forge) },
  plugins: [react()],
  test: { environment: "jsdom", setupFiles: ["./tests/setup.ts"], globals: true },
});
