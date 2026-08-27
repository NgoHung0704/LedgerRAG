/**
 * Fold the built site into ONE self-contained .html file.
 *
 * Gitea has no Pages. Everything else — an Nginx root, Cloudflare, a container
 * in the compose stack — is infrastructure somebody has to own. A single file
 * is not: attach it to a Gitea release, download it, double-click it. It works
 * offline, from file://, with no server and no network, because the script,
 * the styles and both typefaces are inside it.
 *
 * No new dependency: the inlining is a few string replacements over the build
 * Vite already produced.
 *
 *   node tools/bundle.mjs
 *
 * It runs the build itself, with a relative base. Inlining a build made for
 * /LedgerRAG/ would produce a file whose assets point at an absolute path on
 * a host it is not being served from — so the base is not left to the caller.
 */
import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { build } from "vite";

const DIST = new URL("../dist/", import.meta.url).pathname.replace(/^\/(?=[A-Za-z]:)/, "");
const OUT = new URL("../dist-standalone/", import.meta.url).pathname.replace(/^\/(?=[A-Za-z]:)/, "");
const NAME = "ledgerrag-architecture.html";

// index.html's hrefs are relative to dist/; the stylesheet's font urls are
// relative to the STYLESHEET, which lives a directory down in dist/assets/.
const asset = (href, from = DIST) => join(from, href.replace(/^\.?\//, ""));

// Vite's own API rather than a child process: spawning npx needs a shell on
// Windows and a different binary name on each platform, and this has to run
// on a developer's laptop and on a Linux runner alike.
process.env.SITE_BASE = "./";
await build({ root: new URL("..", import.meta.url).pathname.replace(/^\/(?=[A-Za-z]:)/, "") });

let html = await readFile(join(DIST, "index.html"), "utf-8");

// Fonts first: they are referenced from inside the stylesheet, so they have to
// be data URIs before the stylesheet itself is inlined.
const cssHref = html.match(/<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"/)?.[1];
if (!cssHref) throw new Error("no stylesheet in the build");
let css = await readFile(asset(cssHref), "utf-8");

const fontRefs = [...new Set([...css.matchAll(/url\(([^)]*\.woff2)\)/g)]
  .map((m) => m[1].replace(/["']/g, "")))];
for (const ref of fontRefs) {
  const bytes = await readFile(asset(ref, dirname(asset(cssHref))));
  const data = `data:font/woff2;base64,${bytes.toString("base64")}`;
  css = css.split(ref).join(data);
}

const jsSrc = html.match(/<script[^>]+src="([^"]+)"[^>]*><\/script>/)?.[1];
if (!jsSrc) throw new Error("no module script in the build");
const js = await readFile(asset(jsSrc), "utf-8");

// Replaced with FUNCTIONS, not replacement strings: a minified bundle is full
// of $& and $` sequences, and String.replace reads those as instructions to
// paste the match back in. The first version did exactly that and left the
// original <script src> in the output beside the inlined copy.
html = html
  .replace(/<link[^>]+rel="stylesheet"[^>]+>/, () => `<style>
${css}
</style>`)
  // A closing tag inside a string literal would end the script element early.
  .replace(/<script[^>]+src="[^"]+"[^>]*><\/script>/,
           () => `<script type="module">
${js.replace(/<\/script/gi, "<\/script")}
</script>`);

const left = [...html.matchAll(/(?:src|href)="([^"]*\/assets\/[^"]*)"/g)].map((m) => m[1]);
if (left.length) throw new Error(`still referring to files on disk: ${left.join(", ")}`);

await mkdir(OUT, { recursive: true });
await writeFile(join(OUT, NAME), html, "utf-8");
const { size } = await stat(join(OUT, NAME));
console.log(`${NAME}: ${(size / 1024).toFixed(0)} KB, ${fontRefs.length} typefaces inlined`);
