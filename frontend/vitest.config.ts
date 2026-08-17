import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// The i18n module imports through the "@/" alias that Next resolves from
// tsconfig paths; vitest has to be told about it separately.
const here = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: { alias: { "@": here } },
  // node, not jsdom: what is tested here is a pure function. useT() is a
  // three-line wrapper over it and a browser environment would be weight
  // carried for nothing.
  test: { environment: "node", include: ["lib/**/*.test.ts"] },
});
