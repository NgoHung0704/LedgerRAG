/**
 * Open the built page in a real browser and look at it.
 *
 * Two things a unit test cannot see: whether SVG text stays inside its box,
 * and whether the page overflows sideways on a phone. And one thing jsdom
 * checks badly — that switching the language leaves no trace of the other —
 * is asserted here against the real rendered text.
 *
 *   node tools/shots.mjs
 */
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { mkdirSync } from "node:fs";

const DIST = new URL("../dist/", import.meta.url).pathname.replace(/^\//, "");
const OUT = new URL("../shots/", import.meta.url).pathname.replace(/^\//, "");
const BASE = "/LedgerRAG/";
const TYPES = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".svg": "image/svg+xml",
};

const VN = /[ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/;

const server = createServer(async (req, res) => {
  let path = decodeURIComponent(req.url.split("?")[0]);
  if (path.startsWith(BASE)) path = path.slice(BASE.length - 1);
  if (path === "/" || path === "") path = "/index.html";
  try {
    const body = await readFile(join(DIST, normalize(path)));
    res.writeHead(200, { "content-type": TYPES[extname(path)] ?? "application/octet-stream" });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});

await new Promise((r) => server.listen(4173, r));
mkdirSync(OUT, { recursive: true });

const components = JSON.parse(
  await readFile(new URL("../content/components.json", import.meta.url), "utf-8"));
const machines = JSON.parse(
  await readFile(new URL("../content/machines.json", import.meta.url), "utf-8"));

const routes = [
  ["map", "map"],
  ["grid", "grid"],
  ["detail", `c/${components.components[0].id}`],
  ["machine", `machine/${machines.machines[0].id}`],
];
const viewports = [
  ["desktop", { width: 1440, height: 900 }],
  ["phone", { width: 390, height: 844 }],
];

const browser = await chromium.launch();
const problems = [];

for (const [vpName, viewport] of viewports) {
  for (const reduced of vpName === "desktop" ? [false, true] : [false]) {
    const context = await browser.newContext({
      viewport, reducedMotion: reduced ? "reduce" : "no-preference",
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    for (const [name, route] of routes) {
      for (const lang of ["vi", "en"]) {
        await page.goto(`http://localhost:4173${BASE}#/${lang}/${route}`);
        await page.waitForTimeout(250);
        const suffix = reduced ? "-reduced" : "";
        await page.screenshot({
          path: join(OUT, `${vpName}-${name}-${lang}${suffix}.png`),
          fullPage: false,
        });

        // 1. Does the page overflow sideways?
        const overflow = await page.evaluate(() =>
          document.documentElement.scrollWidth - document.documentElement.clientWidth);
        if (overflow > 1) {
          problems.push(`${vpName}/${name}/${lang}: body overflows by ${overflow}px`);
        }

        // 2. Does any SVG label run outside the box it belongs to?
        const spill = await page.evaluate(() => {
          const bad = [];
          document.querySelectorAll("svg").forEach((svg) => {
            svg.querySelectorAll("g[role='img']").forEach((g) => {
              const rect = g.querySelector("rect");
              const text = g.querySelector("text");
              if (!rect || !text) return;
              const r = rect.getBoundingClientRect();
              const t = text.getBoundingClientRect();
              if (t.width === 0) return;
              if (t.left < r.left - 1 || t.right > r.right + 1
                  || t.top < r.top - 1 || t.bottom > r.bottom + 1) {
                bad.push(g.getAttribute("aria-label"));
              }
            });
          });
          return bad;
        });
        spill.forEach((label) =>
          problems.push(`${vpName}/${name}/${lang}: label spills its box: ${label}`));

        // 3. Do two edge labels sit on top of each other?
        const collisions = await page.evaluate(() => {
          const labels = [...document.querySelectorAll("text[data-edge-label]")]
            .map((el) => ({ id: el.dataset.edgeLabel, r: el.getBoundingClientRect() }))
            .filter(({ r }) => r.width > 0 && r.height > 0);
          const hits = [];
          for (let i = 0; i < labels.length; i += 1) {
            for (let j = i + 1; j < labels.length; j += 1) {
              const a = labels[i].r;
              const b = labels[j].r;
              const overlapX = Math.min(a.right, b.right) - Math.max(a.left, b.left);
              const overlapY = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
              if (overlapX > 2 && overlapY > 2) {
                hits.push(`${labels[i].id} ~ ${labels[j].id}`);
              }
            }
          }
          return hits;
        });
        collisions.forEach((pair) =>
          problems.push(`${vpName}/${name}/${lang}: edge labels collide: ${pair}`));

        // 4. The language switch must leave nothing of the other behind.
        const text = await page.evaluate(() => document.body.innerText);
        if (lang === "en" && VN.test(text)) {
          problems.push(
            `${name}/en: Vietnamese letters remain: ${text.match(VN)[0]}`);
        }
      }
    }
    await context.close();
  }
}

await browser.close();
server.close();

console.log(problems.length ? "PROBLEMS:" : "No layout problems found.");
problems.forEach((p) => console.log("  -", p));
process.exit(problems.length ? 1 : 0);
