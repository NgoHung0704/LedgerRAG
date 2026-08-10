import "@testing-library/dom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// The dimming assertions read the COMPUTED opacity, not whether a class name
// is present — a class that no rule matches is exactly the bug they exist to
// catch. So the real stylesheet is loaded into jsdom rather than mocked.
// Read from disk, not imported: `?raw` on a .css file hands back an empty
// string here, which would silently turn the assertion into a no-op.
const style = document.createElement("style");
style.textContent = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf-8");
document.head.appendChild(style);
