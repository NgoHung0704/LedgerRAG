# LedgerRAG Architecture Docs Site — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static, bilingual (VI/EN), keyboard-accessible site on GitHub Pages that explains LedgerRAG's architecture in three layers, whose every claim about the code is held true by drift guards running in the repo's existing pytest gate.

**Architecture:** A separate `docs-site/` (Vite + React + TS, no animation library) renders JSON content from `docs-site/content/`. All reader-visible strings — including button labels and `aria-label`s — live in that content directory, so guards written in Python can check content against source without parsing UI code. Nine guards live in `tests/unit/test_docs_content.py` and therefore run inside `make test-unit`, the gate the repo already has.

**Tech Stack:** Python 3.12 + pytest + `ast` (guards, no new deps) · Vite 5 + React 18 + TypeScript 5 · Vitest + @testing-library/react + jsdom · Playwright (acceptance screenshots only) · GitHub Actions + `actions/deploy-pages`.

**Spec:** [docs/superpowers/specs/2026-08-09-architecture-docs-site-design.md](../specs/2026-08-09-architecture-docs-site-design.md)

## Global Constraints

- **Every reader-visible string lives in `docs-site/content/`.** No string literal in `docs-site/src/` may reach the DOM — not as JSX text, not as `aria-label`, `title`, `alt`, or `placeholder`.
- **Bilingual is a data type, not two files.** Any JSON object containing key `vi` or `en` must contain both, both non-empty strings.
- **`en` strings must contain no Vietnamese-specific letters** (`ăâđêôơư` + tone-marked vowels, both cases). Exempt: `anchor`, `code`, `decl`, `file` — these quote source verbatim.
- **Normalize `\r\n` → `\n` before any text comparison.** The working tree is CRLF on Windows for `.py`/`.tsx` and LF for `.md`; git stores LF. Byte-comparison passes on Windows and fails on the Linux runner.
- **No animation library.** No Motion, no Framer, no GSAP. Transitions are CSS only.
- **Dimming class goes on a parent element**, never on the element whose opacity another rule may set.
- **No exit animation.** Panels unmount immediately; only entry fades.
- **No test hardcodes a count.** No `assert len(x) == 21`, no `expect(n).toBe(20)`. Count from the content itself.
- **Never pipe a gate command through `tail`/`head`.** `cmd | tail -2` returns `tail`'s exit code. Run bare, print the exit code separately.
- **Windows: install `node_modules` with PowerShell, never Git Bash.** Through Git Bash npm misdetects the platform, skips the native optional dependency (rollup) and writes a shim missing its `.cmd`.
- **Vite `base` is `/LedgerRAG/`** and routing is hash-based.
- **Python target:** 3.11+ (`pyproject.toml`), CI uses 3.12. **Node:** CI uses 22.
- **No new Python dependency.** Guards use stdlib `json`, `ast`, `pathlib`, `re`.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `.github/workflows/ci.yml` | The repo's first CI: python gates → docs build → Pages deploy |
| `tests/unit/test_docs_content.py` | G0–G9 drift guards (runs in `make test-unit`) |
| `tests/unit/docs_guard_lib.py` | Shared helpers for the guards: content loading, line reading, source extraction |
| `docs-site/content/ui.json` | Every UI chrome string (nav, buttons, aria-labels, empty states) |
| `docs-site/content/phases.json` | Phase 0–5 + per-phase debts, each cited |
| `docs-site/content/nodes.json` | Layer 1 nodes |
| `docs-site/content/edges.json` | Layer 1 edges + the 61 operations |
| `docs-site/content/ownership.json` | Who owns / who writes each store |
| `docs-site/content/components.json` | Layer 2 grid: 21 components, modules, phase relations |
| `docs-site/content/components/<id>.json` | Layer 3 detail, one file per component |
| `docs-site/content/machines.json` | Two assembly-line diagrams |
| `docs-site/tools/relink.py` | Repairs line numbers that merely drifted |
| `docs-site/src/**` | The site |
| `docs-site/tests/**` | Vitest behaviour tests |

**Modified:** `tablerag/ingestion/tasks.py`, `tablerag/query/steps/rerank.py`, `tests/unit/test_layout_detection.py`, `tests/unit/test_rerank.py`, `tests/unit/test_review_queue.py` (ruff), `.gitignore`, `Makefile`.

---

## Content shapes (referenced by every task)

These are the exact shapes guards and UI both rely on. Localized string is written `L` and means `{"vi": string, "en": string}`.

```jsonc
// citation — two kinds, both verifiable
{ "kind": "excerpt", "file": "tablerag/query/steps/router.py", "from": 41, "to": 58,
  "code": "class SingleKBRouter:\n    async def run…" }
{ "kind": "anchor",  "file": "tablerag/query/steps/router.py", "from": 10, "to": 15,
  "anchor": "degrades to\n  searching ALL KBs, never to searching none" }

// nodes.json
{ "nodes": [ { "id": "api", "kind": "service|store|external|model",
               "column": 0, "label": L, "summary": L,
               "cite": <citation> } ] }

// edges.json
{ "edges": [ { "id": "fe-api-kb", "from": "frontend", "to": "api", "label": L,
               "summary": L,
               "operations": [ { "method": "GET", "path": "/api/kbs",
                                 "auth": L, "request": L, "response": L,
                                 "errors": [ { "code": "404", "meaning": L } ],
                                 "cite": <citation> } ] } ] }

// ownership.json
{ "rows": [ { "store": "postgres", "name": "element",
              "owner": "storage-layer", "writers": ["ingest-page-analysis"],
              "readers": ["http-contracts"], "note": L, "cite": <citation> } ] }

// phases.json
{ "phases": [ { "id": "p2", "label": L, "summary": L, "status": L,
                "cite": <citation>,
                "debts": [ { "text": L, "cite": <citation> } ] } ] }

// components.json
{ "components": [ { "id": "ingest-tables", "group": "ingestion", "label": L,
                    "summary": L,
                    "modules": ["tablerag/ingestion/table_pipeline.py", …],
                    "phases": [ { "id": "p2", "relation": "creates",
                                  "cite": <citation> } ] } ] }

// components/<id>.json
{ "id": "ingest-tables",
  "functions": [ { "name": "parse_table_region",
                   "decl": "def parse_table_region(",
                   "file": "tablerag/ingestion/table_pipeline.py", "line": 88,
                   "note": L } ],
  "flow": { "nodes": [ { "id": "n1", "label": L } ],
            "edges": [ { "from": "n1", "to": "n2", "label": L } ],
            "gates": [ { "id": "g1", "label": L } ],
            "exits": [ { "id": "x1", "label": L } ] },
  "excerpts": [ { "caption": L, "cite": <citation "excerpt"> } ],
  "why":   [ { "text": L, "cite": <citation> } ],
  "debts": [ { "text": L, "cite": <citation> } ] }

// machines.json
{ "machines": [ { "id": "ingest", "label": L,
                  "inlet": { "label": L },
                  "parts": [ { "id": "convert", "component": "ingest-intake",
                               "label": L, "phases": ["p1"] } ],
                  "exits": [ { "id": "done", "label": L } ],
                  "edges": [ { "from": "convert", "to": "extract", "label": L } ] } ] }
```

---

### Task 1: Make both existing gates green, and gate them in CI

The repo has no CI. `pytest tests/unit` passes (843 tests); `ruff check` fails with 6 pre-existing errors. CI cannot gate a red command, so the errors get fixed first.

**The lint gate is not reproducible until it is pinned.** `pyproject.toml`
declares `ruff>=0.4` with no `[tool.ruff.lint] select`, so the effective rule
set moves with the installed version: ruff **0.15.20** (the developer's venv)
reports **6** errors, ruff **0.16.2** (what a fresh `pip install` fetches
today) reports **162**. Twenty of those 162 are `B008` firing on
`user: User = Depends(current_user)` — FastAPI's standard idiom, so the newer
default set is wrong for this repo rather than the repo being wrong. Pin
first, then fix the six.

**Files:**
- Modify: `pyproject.toml`, `tablerag/ingestion/tasks.py:32`, `tablerag/query/steps/rerank.py:17`, `tests/unit/test_layout_detection.py:4`, `tests/unit/test_layout_detection.py:127`, `tests/unit/test_rerank.py:7`, `tests/unit/test_review_queue.py:4`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: a `python-gates` CI job that later tasks extend; a green `ruff check tablerag tests spike` that means the same thing on every machine.

- [ ] **Step 0: Pin the linter so the gate means one thing everywhere**

In `pyproject.toml`, change the `dev` extra's `"ruff>=0.4"` to
`"ruff==0.15.20"`, then reinstall so the local venv matches what CI will get:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install --quiet -e ".[dev]"
& ".\.venv\Scripts\python.exe" -m ruff --version
```

Expected: `ruff 0.15.20`. Without this step the CI lint job fails on 162
findings that have nothing to do with this work.

- [ ] **Step 1: Confirm the failure before fixing it**

```powershell
& ".venv\Scripts\python.exe" -m ruff check tablerag tests spike
Write-Output "RUFF_EXIT=$LASTEXITCODE"
```

Expected: `RUFF_EXIT=1`, "Found 6 errors."

- [ ] **Step 2: Auto-fix the five unused imports**

```powershell
& ".venv\Scripts\python.exe" -m ruff check tablerag tests spike --fix
Write-Output "RUFF_EXIT=$LASTEXITCODE"
```

This removes `TableCtx` from `tablerag/ingestion/tasks.py:32`, `get_settings` from `tablerag/query/steps/rerank.py:17`, `pytest` from `tests/unit/test_layout_detection.py:4` and `tests/unit/test_rerank.py:7`, and `uuid` from `tests/unit/test_review_queue.py:4`. Expected after: 1 remaining error (E402).

- [ ] **Step 3: Fix the E402 by hand**

`tests/unit/test_layout_detection.py` imports `duplicates_table_text, grid_cell_texts` at line 127, mid-file. Move those two names into the existing `from tablerag.ingestion.layout import (…)` block at the top of the file and delete the mid-file import statement. Leave the explanatory comment (`# --- table text must not be indexed twice …`) where it is — it documents the section, not the import.

- [ ] **Step 4: Verify both gates, bare, with separate exit codes**

```powershell
& ".venv\Scripts\python.exe" -m ruff check tablerag tests spike
Write-Output "RUFF_EXIT=$LASTEXITCODE"
& ".venv\Scripts\python.exe" -m pytest tests/unit -q
Write-Output "PYTEST_EXIT=$LASTEXITCODE"
```

Expected: `RUFF_EXIT=0`, "All checks passed!"; `PYTEST_EXIT=0`, `843 passed`. If the test count dropped, an import removal broke a test — investigate before continuing.

- [ ] **Step 5: Create the CI workflow with only the python job**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  python-gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install
        run: pip install -e ".[dev]"
      - name: Lint
        run: ruff check tablerag tests spike
      - name: Unit tests and drift guards
        run: pytest tests/unit -q
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "ci: gate the two commands the repo already has, and make lint green to do it"
```

---

### Task 2: Guard harness — shape, paths, bilingual

Builds the loader every later guard uses, plus the three guards that need no source parsing. Seed content is authored in this task so the guards end green.

**Files:**
- Create: `tests/unit/docs_guard_lib.py`, `tests/unit/test_docs_content.py`, `docs-site/content/ui.json`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `REPO_ROOT`, `CONTENT`, `load(name)`, `load_all()`, `walk(obj)`, `file_lines(rel)`, `norm(s)` — used by every later guard task.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_docs_content.py`:

```python
"""The docs site may not lie about the code.

Every reader-visible claim in docs-site/content/ carries a citation into a
real file, and these guards fail when the two drift apart. They live in
tests/unit because that is the gate the repo already runs (`make test-unit`)
— the site's own toolchain is not required to hold the site honest.
"""

import re

from tests.unit.docs_guard_lib import CONTENT, load_all, walk

VN_LETTERS = re.compile(
    "[ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợ"
    "úùủũụứừửữựýỳỷỹỵÁÀẢÃẠẤẦẨẪẬẮẰẲẴẶÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢ"
    "ÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ]"
)

VERBATIM_FIELDS = {"anchor", "code", "decl", "file"}


def test_every_content_file_parses():
    files = load_all()
    assert files, f"no content found under {CONTENT}"


def test_localized_strings_have_both_languages():
    for path, node in walk(load_all()):
        if not isinstance(node, dict):
            continue
        if "vi" not in node and "en" not in node:
            continue
        for lang in ("vi", "en"):
            value = node.get(lang)
            assert isinstance(value, str) and value.strip(), (
                f"{path}: localized string is missing a non-empty '{lang}' — "
                f"got {node!r}")


def test_english_strings_are_not_untranslated_vietnamese():
    for path, node in walk(load_all()):
        if not isinstance(node, dict) or "en" not in node:
            continue
        hit = VN_LETTERS.search(node["en"])
        assert not hit, (
            f"{path}.en still carries Vietnamese text ({hit.group(0)!r}) — "
            f"{node['en'][:80]!r}")
```

- [ ] **Step 2: Run it to make sure it fails**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/unit/test_docs_content.py -q
Write-Output "EXIT=$LASTEXITCODE"
```

Expected: collection error — `ModuleNotFoundError: tests.unit.docs_guard_lib`.

- [ ] **Step 3: Write the library**

`tests/unit/docs_guard_lib.py`:

```python
"""Shared plumbing for the docs-site drift guards.

Kept apart from the test module so the guards read as assertions rather than
as file handling, and so `docs-site/tools/relink.py` can reuse the exact same
line arithmetic the guards use — a relink that disagreed with the guard would
be worse than no relink at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT = REPO_ROOT / "docs-site" / "content"

# G3 reads ONLY these. A module named anywhere else in content/ — phases.json
# for instance — must not count as documented: a ticket mentioning a file is
# not somebody writing about it.
COMPONENT_FILES = ("components.json",)
COMPONENT_DIR = "components"


def norm(text: str) -> str:
    """CRLF -> LF. Windows checks out .py/.tsx as CRLF and .md as LF while git
    stores LF, so raw comparison is green on Windows and red on the runner."""
    return text.replace("\r\n", "\n")


def load(name: str) -> Any:
    return json.loads((CONTENT / name).read_text(encoding="utf-8"))


def load_all() -> dict[str, Any]:
    """Every content file, keyed by its path relative to content/."""
    out: dict[str, Any] = {}
    for path in sorted(CONTENT.rglob("*.json")):
        key = path.relative_to(CONTENT).as_posix()
        out[key] = json.loads(path.read_text(encoding="utf-8"))
    return out


def load_components() -> dict[str, Any]:
    """The component files, and nothing else — see COMPONENT_FILES."""
    out: dict[str, Any] = {}
    for name in COMPONENT_FILES:
        out[name] = load(name)
    for path in sorted((CONTENT / COMPONENT_DIR).glob("*.json")):
        out[f"{COMPONENT_DIR}/{path.name}"] = json.loads(
            path.read_text(encoding="utf-8"))
    return out


def walk(obj: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Every node in a JSON tree with a dotted path, parents before children."""
    yield path, obj
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk(value, f"{path}.{key}" if path else key)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from walk(value, f"{path}[{i}]")


def citations(files: dict[str, Any]) -> Iterator[tuple[str, dict]]:
    """Every citation object, wherever it sits."""
    for path, node in walk(files):
        if isinstance(node, dict) and node.get("kind") in ("excerpt", "anchor"):
            yield path, node


def file_lines(rel: str) -> list[str]:
    """Normalized lines of a repo file, without their line terminators."""
    return norm((REPO_ROOT / rel).read_text(encoding="utf-8")).split("\n")


def slice_text(rel: str, start: int, end: int) -> str:
    """Lines [start..end], 1-indexed and inclusive, joined with \\n."""
    return "\n".join(file_lines(rel)[start - 1:end])
```

- [ ] **Step 4: Add the path guard to the test module**

Append to `tests/unit/test_docs_content.py`:

```python
from tests.unit.docs_guard_lib import REPO_ROOT, citations


def test_every_declared_path_exists():
    for path, node in walk(load_all()):
        if not isinstance(node, dict) or "file" not in node:
            continue
        target = REPO_ROOT / node["file"]
        assert target.is_file(), (
            f"{path} points at {node['file']}, which does not exist")
```

- [ ] **Step 5: Author the seed content**

`docs-site/content/ui.json` — every chrome string the shell needs. Author it complete; later tasks add keys but never move strings into code.

```json
{
  "siteTitle": { "vi": "Kiến trúc LedgerRAG", "en": "LedgerRAG architecture" },
  "nav": {
    "map":      { "vi": "Bản đồ hệ thống", "en": "System map" },
    "grid":     { "vi": "Component", "en": "Components" },
    "machines": { "vi": "Dây chuyền", "en": "Assembly lines" }
  },
  "actions": {
    "close":         { "vi": "Đóng", "en": "Close" },
    "switchLanguage":{ "vi": "English", "en": "Vietnamese" },
    "openOnGitHub":  { "vi": "Mở trên GitHub", "en": "Open on GitHub" },
    "showTextVersion": { "vi": "Bản văn bản của sơ đồ",
                         "en": "Text version of the diagram" }
  },
  "aria": {
    "closePanel":   { "vi": "Đóng bảng chi tiết", "en": "Close detail panel" },
    "phaseFilter":  { "vi": "Lọc theo giai đoạn", "en": "Filter by phase" },
    "languageSwitch": { "vi": "Chuyển sang tiếng Anh",
                        "en": "Switch to Vietnamese" },
    "_note_language_names": { "vi": "Nhãn nút đổi ngôn ngữ gọi tên ngôn ngữ đích bằng ngôn ngữ đang hiển thị, không phải bằng chính nó — nếu không, chuỗi en sẽ chứa chữ tiếng Việt và vi phạm chính guard G8.",
                              "en": "The language-switch label names the target language in the language currently on screen, not in itself — otherwise the en string would carry Vietnamese letters and break guard G8." },
    "systemMap":    { "vi": "Sơ đồ hệ thống, bấm vào một cạnh để xem hợp đồng",
                      "en": "System map; activate an edge to see its contract" }
  },
  "empty": {
    "noPhaseMatch": { "vi": "Không có component nào thuộc giai đoạn này",
                      "en": "No component belongs to this phase" }
  },
  "labels": {
    "owns":    { "vi": "Sở hữu", "en": "Owns" },
    "writes":  { "vi": "Ghi", "en": "Writes" },
    "reads":   { "vi": "Đọc", "en": "Reads" },
    "debt":    { "vi": "Còn nợ", "en": "Outstanding" },
    "why":     { "vi": "Vì sao viết thế này", "en": "Why it is written this way" },
    "creates":   { "vi": "tạo ra", "en": "creates" },
    "modifies":  { "vi": "sửa", "en": "modifies" },
    "traverses": { "vi": "chạy qua", "en": "runs through" }
  }
}
```

- [ ] **Step 6: Ignore node_modules but keep the lockfile**

Append to `.gitignore`:

```gitignore
# docs-site (the architecture page). Its package-lock.json IS tracked —
# `npm ci` in CI requires a committed lockfile, and the `frontend/` rule
# above deliberately only covers the product app.
docs-site/node_modules/
```

`docs-site/dist/` is already covered by the existing `dist/` rule.

- [ ] **Step 7: Run the guards and see them pass**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/unit/test_docs_content.py -q
Write-Output "EXIT=$LASTEXITCODE"
```

Expected: 4 passed.

- [ ] **Step 8: Prove each guard can fail** — for each, break, run, restore

1. Set `ui.json` → `actions.close.en` to `""` → `test_localized_strings_have_both_languages` fails. Restore.
2. Set `actions.close.en` to `"Đóng"` → `test_english_strings_are_not_untranslated_vietnamese` fails. Restore.
3. Add `{"file": "tablerag/nope.py"}` anywhere in `ui.json` → `test_every_declared_path_exists` fails. Restore.

Record the failure messages; the final report lists which guards were seen red.

- [ ] **Step 9: Commit**

```bash
git add tests/unit/docs_guard_lib.py tests/unit/test_docs_content.py docs-site/content/ui.json .gitignore
git commit -m "docs-site: the guard harness, and the three checks that need no source parsing"
```

---

### Task 3: G1 excerpt verbatim, G2 anchor, and the relink tool

**Files:**
- Modify: `tests/unit/test_docs_content.py`
- Create: `docs-site/tools/relink.py`, `docs-site/content/phases.json`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `slice_text`, `file_lines`, `norm`, `citations` from Task 2.
- Produces: `phases.json` with ids `p0`…`p5` — Tasks 6, 8 and 11 reference these ids.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_docs_content.py`:

```python
from tests.unit.docs_guard_lib import file_lines, norm, slice_text

MIN_ANCHOR = 12


def test_embedded_code_matches_the_file_verbatim():
    for path, cite in citations(load_all()):
        if cite["kind"] != "excerpt":
            continue
        actual = slice_text(cite["file"], cite["from"], cite["to"])
        assert actual == norm(cite["code"]), (
            f"{path}: the excerpt no longer matches "
            f"{cite['file']}:{cite['from']}-{cite['to']}.\n"
            f"--- content says ---\n{norm(cite['code'])}\n"
            f"--- file says ---\n{actual}\n"
            f"If only the line numbers drifted, run `make docs-relink`.")


def test_anchors_sit_inside_their_declared_range():
    for path, cite in citations(load_all()):
        if cite["kind"] != "anchor":
            continue
        anchor = norm(cite["anchor"])
        assert len(anchor) >= MIN_ANCHOR, (
            f"{path}: anchor {anchor!r} is too short to mean anything; "
            f"an anchor must be at least {MIN_ANCHOR} characters")
        whole = norm((REPO_ROOT / cite["file"]).read_text(encoding="utf-8"))
        assert whole.count(anchor) == 1, (
            f"{path}: anchor {anchor!r} occurs {whole.count(anchor)} times in "
            f"{cite['file']} — extend it until it is unique, otherwise "
            f"nothing can tell which occurrence was meant")
        window = slice_text(cite["file"], cite["from"], cite["to"])
        assert anchor in window, (
            f"{path}: anchor {anchor!r} is not inside "
            f"{cite['file']}:{cite['from']}-{cite['to']} any more — the range "
            f"has drifted onto other content. Run `make docs-relink`.")
```

The uniqueness check is what makes bound-checking insufficient into bound-checking sufficient: an anchor that is unique in the file and present in the range pins the citation to one place, so inserting a paragraph above moves the range off it and the guard reddens.

- [ ] **Step 2: Run to verify they fail**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/unit/test_docs_content.py -q
Write-Output "EXIT=$LASTEXITCODE"
```

Expected: PASS — vacuously, because no citation exists yet. This is the case the plan must not mistake for success. Add one deliberately wrong citation to `ui.json`:

```json
"_tmp": { "kind": "anchor", "file": "README.md", "from": 1, "to": 2,
          "anchor": "this string is not in the README" }
```

Re-run. Expected: `test_anchors_sit_inside_their_declared_range` FAILS with "occurs 0 times". Remove `_tmp`.

- [ ] **Step 3: Author `phases.json` with real citations**

Six phases. Every `status` and every `debt` cites README's phase table or SPEC §7. Read the current line numbers first:

```powershell
& ".venv\Scripts\python.exe" -c "
import pathlib
for i, line in enumerate(pathlib.Path('README.md').read_text(encoding='utf-8').split('\n')[13:24], start=14):
    print(i, line[:110])
"
```

Author each phase against what those lines actually say. Shape:

```jsonc
{
  "phases": [
    {
      "id": "p2",
      "label": { "vi": "Phase 2 — sub-pipeline bảng",
                 "en": "Phase 2 — table sub-pipeline" },
      "summary": { "vi": "…", "en": "…" },
      "status": { "vi": "…", "en": "…" },
      "cite": { "kind": "anchor", "file": "README.md", "from": 20, "to": 20,
                "anchor": "make eval-tables` = 88.4%" },
      "debts": [
        { "text": { "vi": "Cổng ≥95% không đạt với qwen3-vl:8b-instruct.",
                    "en": "The ≥95% gate is not met with qwen3-vl:8b-instruct." },
          "cite": { "kind": "anchor", "file": "README.md", "from": 20, "to": 20,
                    "anchor": "≥95% gate is not met with" } }
      ]
    }
  ]
}
```

Do not invent debts. The real ones already written down: Phase 0 final go/no-go pending on real documents; Phase 1 DoD needs a live stack; Phase 2's ≥95% gate unmet; Phase 3's ≥90% recall DoD unachievable on that hardware; Phase 4's one documented miss (a1) and its activation steps; Phase 5's deployment-side DoD.

- [ ] **Step 4: Run and see them pass**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/unit/test_docs_content.py -q
Write-Output "EXIT=$LASTEXITCODE"
```

- [ ] **Step 5: Write the relink tool**

`docs-site/tools/relink.py`:

```python
"""Repair citation line numbers that merely drifted.

The guards demand that an excerpt match its line range verbatim and that an
anchor sit inside its range. Both break when somebody inserts a line above —
which is not an error, just arithmetic. This repairs exactly that case.

It refuses the case that matters: when the cited TEXT itself changed, the
prose explaining it may now be wrong, and a human has to look. Silently
rewriting the page then would defeat the whole point of the guards.

Anchors are relinked by narrowing the range to the anchor's own span. A
narrower range is a stricter guard, so this never weakens a citation.

    python docs-site/tools/relink.py          # report only
    python docs-site/tools/relink.py --write  # rewrite the JSON in place
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.unit.docs_guard_lib import (  # noqa: E402
    CONTENT, REPO_ROOT, file_lines, norm, slice_text,
)


def find_block(lines: list[str], block: list[str]) -> list[int]:
    """1-indexed start lines where `block` appears contiguously."""
    hits = []
    for i in range(len(lines) - len(block) + 1):
        if lines[i:i + len(block)] == block:
            hits.append(i + 1)
    return hits


def relink_excerpt(cite: dict) -> tuple[bool, str]:
    want = norm(cite["code"]).split("\n")
    if slice_text(cite["file"], cite["from"], cite["to"]) == norm(cite["code"]):
        return False, "ok"
    hits = find_block(file_lines(cite["file"]), want)
    if len(hits) != 1:
        return False, (
            f"REFUSED {cite['file']}:{cite['from']}-{cite['to']} — the code "
            f"itself changed ({len(hits)} matches). A human has to check "
            f"whether the text around it is still true.")
    cite["from"], cite["to"] = hits[0], hits[0] + len(want) - 1
    return True, f"moved to {cite['from']}-{cite['to']}"


def relink_anchor(cite: dict) -> tuple[bool, str]:
    anchor = norm(cite["anchor"])
    if anchor in slice_text(cite["file"], cite["from"], cite["to"]):
        return False, "ok"
    want = anchor.split("\n")
    lines = file_lines(cite["file"])
    hits = [i + 1 for i, line in enumerate(lines) if want[0] in line
            and anchor in "\n".join(lines[i:i + len(want)])]
    if len(hits) != 1:
        return False, (
            f"REFUSED {cite['file']}:{cite['from']}-{cite['to']} — anchor "
            f"{anchor[:40]!r} has {len(hits)} matches. Extend the anchor, or "
            f"check whether what it cited still exists.")
    cite["from"], cite["to"] = hits[0], hits[0] + len(want) - 1
    return True, f"narrowed to {cite['from']}-{cite['to']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    changed_files, refused = 0, 0
    for path in sorted(CONTENT.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        touched = False

        def visit(node):
            nonlocal touched, refused
            if isinstance(node, dict):
                if node.get("kind") == "excerpt":
                    moved, msg = relink_excerpt(node)
                elif node.get("kind") == "anchor":
                    moved, msg = relink_anchor(node)
                else:
                    moved, msg = False, "ok"
                if moved:
                    touched = True
                    print(f"{path.name}: {msg}")
                elif msg.startswith("REFUSED"):
                    refused += 1
                    print(msg)
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(data)
        if touched and args.write:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            changed_files += 1

    print(f"\nrewritten: {changed_files} file(s); refused: {refused}")
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Add the Makefile target**

Append to `Makefile`, and add `docs-relink` to the `.PHONY` line:

```makefile
# ---- docs site: repair citation line numbers that merely drifted ----------
# Refuses to touch a citation whose TEXT changed — that needs a human.
docs-relink:
	python docs-site/tools/relink.py --write
```

- [ ] **Step 7: Prove relink works and prove it refuses**

Insert a blank line at the top of `README.md`, run `pytest tests/unit/test_docs_content.py -q` → anchors fail. Run `python docs-site/tools/relink.py --write` → it reports moves. Re-run pytest → green. `git checkout README.md`, then run relink again → it moves them back.

Then change a cited README word so the anchor text no longer exists → relink prints `REFUSED` and exits 1, pytest stays red. Restore.

- [ ] **Step 8: Commit**

```bash
git add tests/unit/test_docs_content.py docs-site/tools/relink.py docs-site/content/phases.json Makefile
git commit -m "docs-site: excerpts must match verbatim, anchors must stay put, and drift alone is repairable"
```

---

### Task 4: G4 — every endpoint documented, in both directions

**Files:**
- Modify: `tests/unit/docs_guard_lib.py`, `tests/unit/test_docs_content.py`
- Create: `docs-site/content/nodes.json`, `docs-site/content/edges.json`

**Interfaces:**
- Consumes: Task 2's loader.
- Produces: `source_endpoints() -> set[tuple[str, str]]`; node ids used by Tasks 5 and 10.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/docs_guard_lib.py`:

```python
import ast


def source_endpoints() -> set[tuple[str, str]]:
    """(METHOD, full path) for every FastAPI route in the API package.

    The full path is the APIRouter prefix plus the decorator path: the nine
    route modules use five different prefixes, so reading the decorator alone
    would document paths that do not exist.
    """
    found: set[tuple[str, str]] = set()
    routes = REPO_ROOT / "tablerag" / "api" / "routes"
    for path in sorted(routes.glob("*.py")):
        tree = ast.parse(norm(path.read_text(encoding="utf-8")))
        prefix = ""
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "APIRouter"):
                for kw in node.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        prefix = kw.value.value
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if (isinstance(deco, ast.Call)
                        and isinstance(deco.func, ast.Attribute)
                        and deco.func.attr in
                        ("get", "post", "put", "patch", "delete")
                        and deco.args
                        and isinstance(deco.args[0], ast.Constant)):
                    found.add((deco.func.attr.upper(),
                               prefix + deco.args[0].value))
    return found
```

Append to `tests/unit/test_docs_content.py`:

```python
from tests.unit.docs_guard_lib import load, source_endpoints


def content_endpoints() -> set[tuple[str, str]]:
    return {(op["method"].upper(), op["path"])
            for edge in load("edges.json")["edges"]
            for op in edge.get("operations", [])}


def test_documented_endpoints_exist_in_the_code():
    missing = sorted(content_endpoints() - source_endpoints())
    assert not missing, (
        "edges.json documents endpoints that no route declares: "
        + ", ".join(f"{m} {p}" for m, p in missing))


def test_every_endpoint_in_the_code_is_documented():
    undocumented = sorted(source_endpoints() - content_endpoints())
    assert not undocumented, (
        "these endpoints exist but no edge documents them — a new endpoint "
        "without a contract is exactly the rot this page exists to prevent: "
        + ", ".join(f"{m} {p}" for m, p in undocumented))
```

- [ ] **Step 2: Run to verify it fails**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/unit/test_docs_content.py -q
Write-Output "EXIT=$LASTEXITCODE"
```

Expected: FAIL — `edges.json` does not exist (FileNotFoundError), then after creating an empty one, `test_every_endpoint_in_the_code_is_documented` fails listing all 61.

- [ ] **Step 3: Dump the real endpoint list to author against**

```powershell
& ".venv\Scripts\python.exe" -c "
import sys; sys.path.insert(0, '.')
from tests.unit.docs_guard_lib import source_endpoints
for m, p in sorted(source_endpoints(), key=lambda x: (x[1], x[0])): print(m, p)
"
```

- [ ] **Step 4: Author `nodes.json`**

Four columns. `column: 0` external, `1` repo services, `2` stores, `3` model endpoints.

Nodes: `browser`, `proxy` (reverse proxy / SSO, header-trusted), `mcp-client`, `consume-dir` · `frontend`, `api`, `worker`, `consumer`, `mcp-server` · `postgres`, `redis`, `qdrant`, `minio` · `parser`, `embedder`, `chat`, `reranker`.

Each node carries a `cite`. For the model roles cite `.env.example`; for services cite `docker-compose.yml`; for the header-trusted proxy cite `tablerag/core/auth.py`.

- [ ] **Step 5: Author `edges.json` covering all 61 operations**

Group operations into edges by contract family, e.g. `fe-api-kb` (KB CRUD), `fe-api-documents`, `fe-api-elements`, `fe-api-chat`, `fe-api-assistants`, `fe-api-models`, `fe-api-health`, `fe-api-me`, `fe-api-diagnostics`, `api-redis-enqueue`, `worker-parser`, `worker-embedder`, `api-chat-model`, `api-reranker`, `api-postgres`, `worker-postgres`, `api-qdrant`, `worker-qdrant`, `api-minio`, `worker-minio`, `consumer-api`, `mcp-api`.

Every operation states method, path, auth, request shape, response shape, error codes, and a `cite` into the handler. Auth comes from `tablerag/core/auth.py` — read it and state the real rule (which paths are open, which need admin), do not guess.

- [ ] **Step 6: Run until both directions are green**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/unit/test_docs_content.py -q
Write-Output "EXIT=$LASTEXITCODE"
```

- [ ] **Step 7: Prove both directions can fail**

1. Change one documented `path` to `/api/does-not-exist` → `test_documented_endpoints_exist_in_the_code` fails. Restore.
2. Delete one operation from `edges.json` → `test_every_endpoint_in_the_code_is_documented` fails naming it. Restore.
3. Add `@router.get("/api/temp-probe")` to `tablerag/api/routes/health.py` → the same test fails. Restore.

- [ ] **Step 8: Commit**

```bash
git add tests/unit/docs_guard_lib.py tests/unit/test_docs_content.py docs-site/content/nodes.json docs-site/content/edges.json
git commit -m "docs-site: layer 1 nodes and contracts, held to the routes in both directions"
```

---

### Task 5: G7 — every store says who writes it

**Files:**
- Modify: `tests/unit/docs_guard_lib.py`, `tests/unit/test_docs_content.py`
- Create: `docs-site/content/ownership.json`

**Interfaces:**
- Consumes: Task 4's node ids.
- Produces: `source_stores() -> set[tuple[str, str]]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/docs_guard_lib.py`:

```python
def source_stores() -> set[tuple[str, str]]:
    """('postgres', tablename) for every ORM model, plus ('qdrant', collection).

    Read from the source rather than listed by hand: a table added without a
    row in the ownership table is precisely the drift this catches.
    """
    found: set[tuple[str, str]] = set()

    orm = ast.parse(norm((REPO_ROOT / "tablerag" / "storage" / "orm.py")
                         .read_text(encoding="utf-8")))
    for node in ast.walk(orm):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if (isinstance(stmt, ast.Assign)
                    and any(getattr(t, "id", None) == "__tablename__"
                            for t in stmt.targets)
                    and isinstance(stmt.value, ast.Constant)):
                found.add(("postgres", stmt.value.value))

    qdrant = ast.parse(norm((REPO_ROOT / "tablerag" / "storage" / "qdrant.py")
                            .read_text(encoding="utf-8")))
    for node in qdrant.body:
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", "").startswith("COLLECTION_")
                        for t in node.targets)
                and isinstance(node.value, ast.Constant)):
            found.add(("qdrant", node.value.value))
    return found
```

Append to `tests/unit/test_docs_content.py`:

```python
from tests.unit.docs_guard_lib import source_stores


def test_every_store_says_who_writes_it():
    rows = {(r["store"], r["name"]) for r in load("ownership.json")["rows"]}
    missing = sorted(source_stores() - rows)
    assert not missing, (
        "no ownership row for: "
        + ", ".join(f"{s}:{n}" for s, n in missing)
        + " — a new store with no stated writer is the single thing new "
          "developers get wrong most often")
    invented = sorted(rows - source_stores())
    assert not invented, (
        "ownership rows for stores that do not exist: "
        + ", ".join(f"{s}:{n}" for s, n in invented))
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL listing 15 Postgres tables + 3 Qdrant collections.

- [ ] **Step 3: Establish who actually writes what before writing a word**

```powershell
& ".venv\Scripts\python.exe" -m pytest --collect-only -q 2>$null | Out-Null
Select-String -Path "tablerag\storage\repositories.py" -Pattern "^def " | Select-Object -First 60
```

Then, for each table, find its writers:

```powershell
Select-String -Path "tablerag\**\*.py" -Pattern "repo\.[a-z_]+\(" | Group-Object Path | Select-Object Count, Name
```

Principle #1 of the SPEC says `ingestion/` and `query/` meet only in storage — the ownership table is where that principle becomes visible, so get it right from the call sites, not from intuition.

- [ ] **Step 4: Author `ownership.json`**

One row per store, with `owner` (the component that defines the schema), `writers`, `readers`, a localized `note` saying what the store is for, and a `cite`. Writers must name components defined in Task 6 — use the ids from the spec's §7 table.

- [ ] **Step 5: Run and see green**

- [ ] **Step 6: Prove it fails**

Add a class with `__tablename__ = "probe_tmp"` to `tablerag/storage/orm.py` → the guard fails naming it. Restore. Then delete a row from `ownership.json` → fails. Restore.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/docs_guard_lib.py tests/unit/test_docs_content.py docs-site/content/ownership.json
git commit -m "docs-site: who owns and who writes every store, checked against the ORM"
```

---

### Task 6: G3 module coverage and G6 cross-references

**Files:**
- Modify: `tests/unit/docs_guard_lib.py`, `tests/unit/test_docs_content.py`
- Create: `docs-site/content/components.json`

**Interfaces:**
- Consumes: phase ids from Task 3, node ids from Task 4.
- Produces: the 21 component ids; Task 7 creates one detail file per id.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/docs_guard_lib.py`:

```python
SOURCE_GLOBS = (
    ("tablerag", "**/*.py"),
    ("frontend/app", "**/*.ts"), ("frontend/app", "**/*.tsx"),
    ("frontend/components", "**/*.ts"), ("frontend/components", "**/*.tsx"),
    ("frontend/lib", "**/*.ts"), ("frontend/lib", "**/*.tsx"),
)


def source_modules() -> set[str]:
    """Every module the page is required to account for.

    Scope agreed in the spec: tablerag/ + frontend/{app,components,lib}.
    Build output and caches are excluded by anchoring on those three
    frontend subdirectories rather than on frontend/ itself.
    """
    found: set[str] = set()
    for base, pattern in SOURCE_GLOBS:
        for path in (REPO_ROOT / base).glob(pattern):
            if "__pycache__" in path.parts or "node_modules" in path.parts:
                continue
            found.add(path.relative_to(REPO_ROOT).as_posix())
    return found
```

Append to `tests/unit/test_docs_content.py`:

```python
from tests.unit.docs_guard_lib import load_components, source_modules


def documented_modules() -> set[str]:
    """Modules named by a COMPONENT file — nothing else counts.

    Deliberately not `load_all()`: if a module merely appearing in
    phases.json counted, a file a ticket happens to mention would pass as
    documented while nobody had written a line about it.
    """
    out: set[str] = set()
    for name, data in load_components().items():
        for component in data.get("components", []):
            out.update(component.get("modules", []))
    return out


def test_every_source_module_appears_in_a_component():
    missing = sorted(source_modules() - documented_modules())
    assert not missing, (
        f"{len(missing)} module(s) belong to no component — add a new file "
        f"without writing about it and this is what goes red:\n  "
        + "\n  ".join(missing))


def test_components_do_not_claim_modules_that_do_not_exist():
    invented = sorted(documented_modules() - source_modules())
    assert not invented, "components claim non-existent modules:\n  " + \
        "\n  ".join(invented)


def test_component_ids_are_unique():
    ids = [c["id"] for c in load("components.json")["components"]]
    assert len(ids) == len(set(ids)), \
        f"duplicate component id(s): {sorted({i for i in ids if ids.count(i) > 1})}"


def test_every_phase_reference_resolves():
    phases = {p["id"] for p in load("phases.json")["phases"]}
    for component in load("components.json")["components"]:
        for rel in component["phases"]:
            assert rel["id"] in phases, (
                f"component {component['id']} references unknown phase "
                f"{rel['id']}")
            assert rel["relation"] in ("creates", "modifies", "traverses"), (
                f"component {component['id']} uses unknown relation "
                f"{rel['relation']!r}")


def test_every_phase_is_owned_by_something():
    """The reverse direction. `traverses` does not count: a phase whose only
    tie to the code is 'the request passes through here' owns nothing, and
    would vanish from the diagram the moment anyone filtered by it."""
    owned = {rel["id"]
             for component in load("components.json")["components"]
             for rel in component["phases"]
             if rel["relation"] in ("creates", "modifies")}
    orphans = sorted({p["id"] for p in load("phases.json")["phases"]} - owned)
    assert not orphans, (
        f"phase(s) {orphans} are created or modified by no component — "
        f"filtering by them would light up nothing")


def test_ownership_rows_name_real_components():
    ids = {c["id"] for c in load("components.json")["components"]}
    for row in load("ownership.json")["rows"]:
        for who in [row["owner"], *row["writers"], *row["readers"]]:
            assert who in ids, (
                f"ownership row {row['store']}:{row['name']} names unknown "
                f"component {who!r}")


def test_edges_connect_declared_nodes_and_every_node_is_connected():
    ids = {n["id"] for n in load("nodes.json")["nodes"]}
    touched: set[str] = set()
    for edge in load("edges.json")["edges"]:
        for end in ("from", "to"):
            assert edge[end] in ids, \
                f"edge {edge['id']} points at unknown node {edge[end]!r}"
            touched.add(edge[end])
    stranded = sorted(ids - touched)
    assert not stranded, (
        f"node(s) {stranded} are on the map but no edge reaches them — "
        f"either wire them up or take them off")
```

- [ ] **Step 2: Run to verify they fail**

Expected: `test_every_source_module_appears_in_a_component` fails listing 105 modules.

- [ ] **Step 3: Author `components.json`**

Use the spec's §7 mapping verbatim — it already accounts for all 73 Python modules and all 32 frontend files. For each component write `label`, `summary`, `modules`, and `phases` with the three relation kinds.

Deriving the relations: read SPEC §4 for what each phase builds, and README's phase table for what shipped. Every relation carries a `cite` into SPEC or README. Commit mapping cannot be used — commits are not tagged by phase.

Worked example for `query-route-retrieve`: `creates` p1 (the router slot ships in the skeleton), `modifies` p4 (hybrid retrieval + rerank), `modifies` p5 (`LLMRouter`) — and `traverses` p2 nowhere, because Phase 2 requests do not run through it.

Worked example for `storage-layer`: `creates` p1, `modifies` p2 (records/table_element), and `traverses` p4 — a Phase 4 answer reads through storage without Phase 4 having changed it. Without that `traverses`, a reader filtering to Phase 4 would see the retrieval path stop dead at a gap.

- [ ] **Step 4: Run until every guard is green**

Iterate: the failure message lists exactly which modules are still unaccounted for.

- [ ] **Step 5: Prove each new guard fails**

1. `New-Item docs-site/../tablerag/probe_tmp.py` → coverage guard fails naming it. Delete.
2. Add `"tablerag/nope.py"` to a component's `modules` → `test_components_do_not_claim_modules_that_do_not_exist` fails. Restore.
3. Change every `creates`/`modifies` for one phase to `traverses` → `test_every_phase_is_owned_by_something` fails naming it. Restore.
4. Point one edge `to` at `"nowhere"` → the edge guard fails. Restore.
5. Add a node with no edge → the stranded-node half fails. Restore.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/docs_guard_lib.py tests/unit/test_docs_content.py docs-site/content/components.json
git commit -m "docs-site: the component grid, and the guard that goes red when a module has no home"
```

---

### Task 7: Layer 3 detail — 21 files, each cited

**Files:**
- Create: `docs-site/content/components/<id>.json` × 21
- Modify: `tests/unit/test_docs_content.py`

**Interfaces:**
- Consumes: component ids from Task 6.
- Produces: `functions[]`, `flow`, `excerpts[]`, `why[]`, `debts[]` per component — Task 12 renders these.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_docs_content.py`:

```python
def test_every_component_has_exactly_one_detail_file():
    listed = {c["id"] for c in load("components.json")["components"]}
    detail = {name.split("/")[1][:-5]
              for name in load_components() if name.startswith("components/")}
    assert listed == detail, (
        f"components without a detail file: {sorted(listed - detail)}; "
        f"detail files with no component: {sorted(detail - listed)}")


def test_detail_file_id_matches_its_filename():
    for name, data in load_components().items():
        if not name.startswith("components/"):
            continue
        assert data["id"] == name.split("/")[1][:-5], \
            f"{name} declares id {data['id']!r}"


def test_function_declarations_sit_on_the_line_they_claim():
    for name, data in load_components().items():
        for fn in data.get("functions", []):
            whole = norm((REPO_ROOT / fn["file"]).read_text(encoding="utf-8"))
            assert whole.count(fn["decl"]) == 1, (
                f"{name}: {fn['decl']!r} occurs {whole.count(fn['decl'])} "
                f"times in {fn['file']} — extend it until it is unique")
            line = file_lines(fn["file"])[fn["line"] - 1]
            assert fn["decl"] in line, (
                f"{name}: {fn['file']}:{fn['line']} is {line.strip()!r}, "
                f"not {fn['decl']!r}. Run `make docs-relink`.")
            assert fn["name"] in fn["decl"], \
                f"{name}: function name {fn['name']!r} is not in its declaration"


def test_flow_diagrams_are_internally_connected():
    for name, data in load_components().items():
        flow = data.get("flow")
        if not flow:
            continue
        ids = ({n["id"] for n in flow["nodes"]}
               | {g["id"] for g in flow.get("gates", [])}
               | {x["id"] for x in flow.get("exits", [])})
        for edge in flow["edges"]:
            for end in ("from", "to"):
                assert edge[end] in ids, \
                    f"{name}: flow edge points at unknown step {edge[end]!r}"
```

- [ ] **Step 2: Run to verify they fail**

Expected: `test_every_component_has_exactly_one_detail_file` fails listing all 21.

- [ ] **Step 3: Add the relink support for `decl`**

In `docs-site/tools/relink.py`, extend `visit` to also handle function entries — a dict with `decl`, `file`, `line`:

```python
def relink_decl(fn: dict) -> tuple[bool, str]:
    lines = file_lines(fn["file"])
    if fn["decl"] in lines[fn["line"] - 1]:
        return False, "ok"
    hits = [i + 1 for i, line in enumerate(lines) if fn["decl"] in line]
    if len(hits) != 1:
        return False, (
            f"REFUSED {fn['file']}:{fn['line']} — {fn['decl']!r} has "
            f"{len(hits)} matches; the declaration itself changed.")
    fn["line"] = hits[0]
    return True, f"moved to line {fn['line']}"
```

Call it from `visit` when `"decl" in node and "line" in node`.

- [ ] **Step 4: Author the 21 detail files**

For each component: 5–10 `functions` (the ones a newcomer must know, not all of them), a `flow` with real gate labels, 1–3 `excerpts`, `why` cards, and `debts` where debt exists.

The `why` cards must be **rewritten from reasons already in the code**, not invented. The docstring at the head of `tablerag/query/steps/router.py` states three: KB isolation is the founding idea; the swap was plug-in only because everything downstream filters on `routed_kb_ids`; and a router failure degrades to searching all KBs because searching nothing is a dead end. Each becomes a card with an anchor into that docstring.

Do the same for the rest: `docker-compose.yml` explains the Qdrant `nofile` limit and worker concurrency; `.env.example` explains the `qwen3-vl` `-instruct` tag; `tests/unit/test_architecture.py` explains principle #1. Where no reason is written down, write no card.

- [ ] **Step 5: Run until green**

- [ ] **Step 6: Prove the function guard fails**

Insert a blank line above a cited function → `test_function_declarations_sit_on_the_line_they_claim` fails. Run `make docs-relink` → green. Undo the blank line, relink again.

Then rename a cited function in the source → relink prints `REFUSED` and the guard stays red. Restore.

- [ ] **Step 7: Commit**

```bash
git add docs-site/content/components docs-site/tools/relink.py tests/unit/test_docs_content.py
git commit -m "docs-site: layer 3 — real functions, real code, and reasons taken from the code that states them"
```

---

### Task 8: The two assembly lines

**Files:**
- Create: `docs-site/content/machines.json`
- Modify: `tests/unit/test_docs_content.py`

**Interfaces:**
- Consumes: component ids (Task 6), phase ids (Task 3).
- Produces: `machines[]` — Task 13 renders it.

- [ ] **Step 1: Write the failing test**

```python
def test_machine_parts_name_real_components_and_phases():
    components = {c["id"] for c in load("components.json")["components"]}
    phases = {p["id"] for p in load("phases.json")["phases"]}
    for machine in load("machines.json")["machines"]:
        part_ids = {p["id"] for p in machine["parts"]}
        exit_ids = {x["id"] for x in machine["exits"]}
        for part in machine["parts"]:
            assert part["component"] in components, (
                f"machine {machine['id']}: part {part['id']} names unknown "
                f"component {part['component']!r}")
            for phase in part["phases"]:
                assert phase in phases, (
                    f"machine {machine['id']}: part {part['id']} names "
                    f"unknown phase {phase!r}")
        for edge in machine["edges"]:
            for end in ("from", "to"):
                assert edge[end] in part_ids | exit_ids, (
                    f"machine {machine['id']}: edge points at unknown "
                    f"part/exit {edge[end]!r}")


def test_every_machine_part_is_reachable_from_the_inlet():
    """A part nothing feeds is a drawing mistake, not a pipeline."""
    for machine in load("machines.json")["machines"]:
        parts = [p["id"] for p in machine["parts"]]
        reached = {parts[0]}
        for _ in parts:
            for edge in machine["edges"]:
                if edge["from"] in reached:
                    reached.add(edge["to"])
        unreachable = sorted(set(parts) - reached)
        assert not unreachable, (
            f"machine {machine['id']}: {unreachable} cannot be reached from "
            f"the inlet")
```

- [ ] **Step 2: Run to verify it fails** — `machines.json` does not exist.

- [ ] **Step 3: Author `machines.json`**

Two machines.

`ingest`: inlet = a PDF (or an Office file, converted). Parts in order — `convert` → `extract` → `layout` → `regions` → `tables` → `figures` → `confidence` → `chunk` → `embed` → `index`. Exits — `done`, `failed`, `review` (the confidence queue). Each part names its component and the phases it belongs to.

`query`: inlet = a question. Parts — `router` → `retrieve` → `rerank` → `assemble` → `generate` → `verify`. Exits — `answered` (with citations), `refused`, `flagged`. Gate labels must be real: the router's degrade-to-all-KBs branch, the verifier's number check.

- [ ] **Step 4: Run and see green**

- [ ] **Step 5: Prove it fails** — point one edge `to` at `"ghost"` → both guards fail. Add a part with no incoming edge → the reachability guard fails naming it. Restore.

- [ ] **Step 6: Commit**

```bash
git add docs-site/content/machines.json tests/unit/test_docs_content.py
git commit -m "docs-site: the two assembly lines, with their real branches and exits"
```

---

### Task 9: Site scaffold — routing, Escape, language, and G9

**Files:**
- Create: `docs-site/package.json`, `docs-site/vite.config.ts`, `docs-site/tsconfig.json`, `docs-site/index.html`, `docs-site/src/main.tsx`, `docs-site/src/App.tsx`, `docs-site/src/route.ts`, `docs-site/src/content.ts`, `docs-site/src/i18n.ts`, `docs-site/src/styles.css`, `docs-site/tests/route.test.tsx`, `docs-site/tests/setup.ts`
- Modify: `tests/unit/test_docs_content.py`

**Interfaces:**
- Produces: `useRoute()`, `navigate(segments)`, `Lang`, `t(key)`, `useLang()` — every later UI task consumes these.

- [ ] **Step 1: Install with PowerShell**

```powershell
New-Item -ItemType Directory -Force docs-site | Out-Null
Set-Location docs-site
npm init -y
npm install react react-dom
npm install -D vite @vitejs/plugin-react typescript @types/react @types/react-dom vitest @testing-library/react @testing-library/dom jsdom @types/node
Set-Location ..
Write-Output "NPM_EXIT=$LASTEXITCODE"
```

**PowerShell, not Git Bash.** Through Git Bash npm misdetects the platform, skips rollup's native optional dependency and writes a `vite` shim without its `.cmd`.

- [ ] **Step 2: Write the failing behaviour test**

`docs-site/tests/route.test.tsx`:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { parseRoute, formatRoute, popOne } from "../src/route";

describe("route", () => {
  beforeEach(() => { window.location.hash = ""; });

  it("round-trips every segment", () => {
    const r = parseRoute("#/vi/c/ingest-tables/fn/parse_table_region");
    expect(r.lang).toBe("vi");
    expect(r.view).toBe("c");
    expect(r.id).toBe("ingest-tables");
    expect(r.sub).toEqual({ kind: "fn", id: "parse_table_region" });
    expect(formatRoute(r)).toBe("#/vi/c/ingest-tables/fn/parse_table_region");
  });

  it("Escape peels exactly one layer, not the whole stack", () => {
    const deep = parseRoute("#/vi/c/ingest-tables/fn/parse_table_region");
    const once = popOne(deep);
    expect(formatRoute(once)).toBe("#/vi/c/ingest-tables");
    const twice = popOne(once);
    expect(formatRoute(twice)).toBe("#/vi/grid");
  });

  it("keeps the language when a layer is peeled", () => {
    const r = popOne(parseRoute("#/en/c/ingest-tables/fn/x"));
    expect(r.lang).toBe("en");
  });
});
```

- [ ] **Step 3: Run to verify it fails**

```powershell
Set-Location docs-site; npx vitest run; Write-Output "EXIT=$LASTEXITCODE"; Set-Location ..
```

Expected: FAIL — `../src/route` not found.

- [ ] **Step 4: Write the router**

`docs-site/src/route.ts`:

```ts
export type Lang = "vi" | "en";
export type View = "map" | "grid" | "c" | "machine";
export type Sub = { kind: "edge" | "fn" | "excerpt"; id: string } | null;

export interface Route {
  lang: Lang; view: View; id: string | null; sub: Sub; phase: string | null;
}

const DEFAULT: Route = {
  lang: "vi", view: "map", id: null, sub: null, phase: null,
};

export function parseRoute(hash: string): Route {
  const [pathPart, queryPart] = hash.replace(/^#\/?/, "").split("?");
  const parts = pathPart.split("/").filter(Boolean);
  const phase = new URLSearchParams(queryPart ?? "").get("phase");
  if (parts.length === 0) return { ...DEFAULT, phase };
  const [lang, view, id, subKind, subId] = parts;
  return {
    lang: lang === "en" ? "en" : "vi",
    view: (["map", "grid", "c", "machine"].includes(view) ? view : "map") as View,
    id: id ?? null,
    sub: subKind && subId
      ? { kind: subKind as "edge" | "fn" | "excerpt", id: subId }
      : null,
    phase,
  };
}

export function formatRoute(r: Route): string {
  const parts = [r.lang, r.view];
  if (r.id) parts.push(r.id);
  if (r.sub) parts.push(r.sub.kind, r.sub.id);
  const query = r.phase ? `?phase=${encodeURIComponent(r.phase)}` : "";
  return `#/${parts.join("/")}${query}`;
}

/** One layer, once. Escape and Back must agree, and neither may skip a rung. */
export function popOne(r: Route): Route {
  if (r.sub) return { ...r, sub: null };
  if (r.view === "c") return { ...r, view: "grid", id: null };
  if (r.view === "machine") return { ...r, view: "grid", id: null };
  if (r.view === "grid") return { ...r, view: "map", id: null };
  return r;
}
```

- [ ] **Step 5: Write the single Escape owner**

`docs-site/src/App.tsx` holds the only `keydown` listener in the app:

```tsx
// One listener, owned by the thing that owns the route.
//
// stopPropagation does NOT stop other listeners bound to the same target, so
// a panel that listens on `document` itself would let one Escape close the
// whole stack and push several history entries. And a mount-order stack is
// worse: a panel still playing its exit would sit in it and swallow the next
// key. Neither exists here — panels render from the route and unmount at once.
useEffect(() => {
  function onKey(event: KeyboardEvent) {
    if (event.key !== "Escape") return;
    const current = parseRoute(window.location.hash);
    const next = popOne(current);
    if (formatRoute(next) === formatRoute(current)) return;
    if ((window.history.state?.depth ?? 0) > 0) window.history.back();
    else window.history.replaceState({ depth: 0 }, "", formatRoute(next));
    // replaceState does not fire hashchange; tell the app ourselves.
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  }
  document.addEventListener("keydown", onKey);
  return () => document.removeEventListener("keydown", onKey);
}, []);
```

`navigate` in `route.ts` pushes with an incremented depth:

```ts
export function navigate(next: Route): void {
  const depth = (window.history.state?.depth ?? 0) + 1;
  window.history.pushState({ depth }, "", formatRoute(next));
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}
```

- [ ] **Step 6: Write `i18n.ts` and `content.ts`**

`content.ts` imports every JSON file statically (Vite inlines them, so the built site is one bundle and no fetch can fail):

```ts
import ui from "../content/ui.json";
import nodes from "../content/nodes.json";
import edges from "../content/edges.json";
import ownership from "../content/ownership.json";
import phases from "../content/phases.json";
import components from "../content/components.json";
import machines from "../content/machines.json";

// 21 detail files, keyed by component id. Globbed rather than imported one
// by one so adding a component is a content change, not a code change —
// which is the whole premise of the guards.
const details = import.meta.glob("../content/components/*.json",
                                 { eager: true, import: "default" });

export const componentDetails: Record<string, ComponentDetail> =
  Object.fromEntries(Object.entries(details).map(([path, value]) =>
    [path.split("/").pop()!.replace(/\.json$/, ""), value as ComponentDetail]));

export const content = {
  ui, nodes, edges, ownership, phases, components, machines, componentDetails,
};
```

**`content.componentDetails[id]` is the only way to read a Layer 3 file.**
Every task that touches detail content uses this accessor — never a raw
path key.

`i18n.ts` resolves a localized value; **it never contains a string**:

```ts
export type L = { vi: string; en: string };
export const pick = (value: L, lang: Lang): string => value[lang];
```

- [ ] **Step 7: Configure Vite for the Pages base path**

`docs-site/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // Pages serves a project site from /<repo>/. Getting this wrong yields a
  // blank page with no error, which is worse than a crash.
  base: "/LedgerRAG/",
  plugins: [react()],
  test: { environment: "jsdom", setupFiles: ["./tests/setup.ts"], globals: true },
});
```

- [ ] **Step 8: Run the behaviour test and see it pass**

- [ ] **Step 9: Add G9 — no strings in code**

Append to `tests/unit/test_docs_content.py`:

```python
import re

SITE_SRC = REPO_ROOT / "docs-site" / "src"
ATTR_LITERAL = re.compile(r'\b(aria-label|title|alt|placeholder)\s*=\s*"')
JSX_TEXT = re.compile(r">\s*([^<>{}\n]*[A-Za-zÀ-ỹ][^<>{}]*)<")


def test_no_reader_visible_string_lives_in_the_site_code():
    """Content is in JSON so guards can check it in the repo's own language.
    A label that slips into a .tsx escapes every check in this file."""
    problems = []
    for path in sorted(SITE_SRC.rglob("*.tsx")):
        text = norm(path.read_text(encoding="utf-8"))
        for i, line in enumerate(text.split("\n"), start=1):
            if ATTR_LITERAL.search(line):
                problems.append(f"{path.name}:{i} literal attribute: {line.strip()}")
            for hit in JSX_TEXT.finditer(line):
                problems.append(f"{path.name}:{i} literal text: {hit.group(1).strip()!r}")
    assert not problems, (
        "these strings must come from docs-site/content/:\n  "
        + "\n  ".join(problems))
```

- [ ] **Step 10: Run it, see it green, then prove it red**

Add `aria-label="Close"` to any element in `App.tsx` → the guard fails. Replace with `aria-label={pick(content.ui.aria.closePanel, lang)}` → green. Add a bare `<span>Hello</span>` → fails. Remove.

- [ ] **Step 11: Commit**

```bash
git add docs-site tests/unit/test_docs_content.py
git commit -m "docs-site: the shell — one Escape owner, hash routes, and no string allowed in the code"
```

---

### Task 10: Layer 1 — the map, its lanes, and its text version

**Files:**
- Create: `docs-site/src/svg/layout.ts`, `docs-site/src/views/SystemMap.tsx`, `docs-site/src/views/ContractPanel.tsx`, `docs-site/src/views/DiagramText.tsx`, `docs-site/tests/svg.test.ts`, `docs-site/tests/map.test.tsx`

**Interfaces:**
- Consumes: `content.nodes`, `content.edges`, `pick`, `navigate`.
- Produces, all from `src/svg/layout.ts`: `wrapLabel(text, maxChars) -> string[]`, `boxHeight(lines) -> number`, `nodeHeight(node) -> number`, `laneOffsets(count) -> number[]`, `columnGap(maxLanes) -> number`.

- [ ] **Step 1: Write the failing tests**

`docs-site/tests/svg.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { wrapLabel, boxHeight, nodeHeight, laneOffsets, columnGap } from "../src/svg/layout";
import { content } from "../src/content";
import { pick } from "../src/i18n";

describe("svg text", () => {
  it("wraps a long label instead of letting it run out of its box", () => {
    const lines = wrapLabel("Reverse proxy and single sign-on, header trusted", 18);
    expect(lines.length).toBeGreaterThan(1);
    lines.forEach((line) => expect(line.length).toBeLessThanOrEqual(18));
  });

  it("grows the box with the number of lines", () => {
    expect(boxHeight(wrapLabel("short", 18))).toBeLessThan(
      boxHeight(wrapLabel("Reverse proxy and single sign-on, header trusted", 18)));
  });

  it("sizes every node for whichever language is longer", () => {
    // counted from the content, never hardcoded
    content.nodes.nodes.forEach((node) => {
      const vi = boxHeight(wrapLabel(pick(node.label, "vi"), 18));
      const en = boxHeight(wrapLabel(pick(node.label, "en"), 18));
      expect(nodeHeight(node)).toBe(Math.max(vi, en));
    });
  });
});

describe("edge lanes", () => {
  it("gives parallel edges distinct lanes", () => {
    const offsets = laneOffsets(5);
    expect(new Set(offsets).size).toBe(5);
  });

  it("widens the gap so five lines are not crushed into forty pixels", () => {
    expect(columnGap(5)).toBeGreaterThan(columnGap(1));
    expect(columnGap(5)).toBeGreaterThanOrEqual(5 * 24);
  });
});
```

`docs-site/tests/map.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SystemMap } from "../src/views/SystemMap";
import { content } from "../src/content";
import { pick } from "../src/i18n";

describe("system map", () => {
  it("puts two edges between the same pair on different paths", () => {
    const { container } = render(<SystemMap lang="vi" phase={null} />);
    const pairs = new Map<string, string[]>();
    content.edges.edges.forEach((edge) => {
      const key = [edge.from, edge.to].sort().join("~");
      const d = container.querySelector<SVGPathElement>(
        `path[data-edge="${edge.id}"]`)!.getAttribute("d")!;
      pairs.set(key, [...(pairs.get(key) ?? []), d]);
    });
    pairs.forEach((ds) => expect(new Set(ds).size).toBe(ds.length));
  });

  it("puts each edge label at the middle of its own turn, not the source box", () => {
    const { container } = render(<SystemMap lang="vi" phase={null} />);
    const points = content.edges.edges.map((edge) => {
      const label = container.querySelector(`text[data-edge-label="${edge.id}"]`)!;
      return `${label.getAttribute("x")},${label.getAttribute("y")}`;
    });
    expect(new Set(points).size).toBe(points.length);
  });

  it("every clickable shape is reachable and announced", () => {
    render(<SystemMap lang="vi" phase={null} />);
    content.edges.edges.forEach((edge) => {
      const el = screen.getByLabelText(pick(edge.label, "vi"));
      expect(el.getAttribute("tabindex")).toBe("0");
      expect(el.closest("[aria-hidden='true']")).toBeNull();
    });
  });

  it("the text version carries the edge labels AND the gate labels", () => {
    render(<SystemMap lang="vi" phase={null} />);
    const text = screen.getByTestId("diagram-text").textContent ?? "";
    content.edges.edges.forEach((edge) => {
      expect(text).toContain(pick(edge.label, "vi"));
    });
    content.nodes.nodes.forEach((node) => {
      expect(text).toContain(pick(node.label, "vi"));
    });
  });
});
```

The last assertion is the one that matters: a function list is not a substitute for a diagram, because it carries neither edge labels nor branch labels — all of the logic, in other words.

- [ ] **Step 2: Run to verify they fail** — modules do not exist yet.

- [ ] **Step 3: Implement `src/svg/layout.ts`**

```ts
export const LINE_HEIGHT = 16;
export const BOX_PADDING = 12;
export const LANE_PITCH = 24;

/** SVG <text> does not wrap. Break it here or it runs over its neighbour. */
export function wrapLabel(text: string, maxChars: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (candidate.length > maxChars && line) { lines.push(line); line = word; }
    else line = candidate;
  }
  if (line) lines.push(line);
  return lines;
}

export const boxHeight = (lines: string[]): number =>
  lines.length * LINE_HEIGHT + BOX_PADDING * 2;

/** Symmetric offsets so n parallel edges never share a path. */
export function laneOffsets(count: number): number[] {
  const mid = (count - 1) / 2;
  return Array.from({ length: count }, (_, i) => (i - mid) * LANE_PITCH);
}

/** A column gap must fit the lines crossing it. Five will not live in 40px. */
export const columnGap = (maxLanes: number): number =>
  Math.max(160, maxLanes * LANE_PITCH + 80);

/** A node is sized for the LONGER language, so switching never overflows it. */
export const nodeHeight = (node: { label: { vi: string; en: string } }): number =>
  Math.max(boxHeight(wrapLabel(node.label.vi, LABEL_CHARS)),
           boxHeight(wrapLabel(node.label.en, LABEL_CHARS)));

export const LABEL_CHARS = 18;
```

`svg.test.ts` imports `nodeHeight` alongside the rest; the test that sizes
every node for the longer language is checking exactly this function.

- [ ] **Step 4: Implement `SystemMap.tsx`**

Rules the tests pin down: render each label as `<tspan>` per wrapped line; give each edge `data-edge` and its label `data-edge-label`; compute the label anchor at the midpoint of the **turn segment**, not the source box centre — two edges leaving the same node in different directions would otherwise land on the same coordinate; make every interactive shape `<g role="button" tabIndex={0} aria-label={…} onClick onKeyDown>`; never set `aria-hidden` on the SVG.

- [ ] **Step 5: Implement `DiagramText.tsx`**

Generated from the same JSON the SVG reads, so it cannot drift from the picture: a list of nodes with their summaries, then every edge as "from → to: label", then gates and exits where the diagram has them. Rendered inside a `<details>` with `data-testid="diagram-text"`.

- [ ] **Step 6: Run the tests and see them pass**

- [ ] **Step 7: Prove each test fails**

1. Return `[text]` from `wrapLabel` → wrap tests fail.
2. Return `0` from every `laneOffsets` entry → the distinct-paths test fails.
3. Use the source box centre for the label anchor → the distinct-label-position test fails.
4. Add `aria-hidden="true"` to the SVG root → the announced test fails.
5. Drop gate/edge labels from `DiagramText` → the text-version test fails.

Restore each.

- [ ] **Step 8: Commit**

```bash
git add docs-site
git commit -m "docs-site: layer 1 — lanes that do not overlap, labels that do not collide, a text version that does not lie"
```

---

### Task 11: Layer 2 — the grid and the phase filter

**Files:**
- Create: `docs-site/src/views/ComponentGrid.tsx`, `docs-site/src/views/PhaseFilter.tsx`, `docs-site/tests/filter.test.tsx`

**Interfaces:**
- Consumes: `content.components`, `content.phases`, route `phase`.
- Produces: `matchesPhase(component, phase) -> boolean`.

- [ ] **Step 1: Write the failing test**

`docs-site/tests/filter.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComponentGrid } from "../src/views/ComponentGrid";
import { matchesPhase } from "../src/views/PhaseFilter";
import { content } from "../src/content";

describe("phase filter", () => {
  it("dims through a parent, so nothing on the card fights the opacity", () => {
    const phase = content.phases.phases[0].id;
    const { container } = render(<ComponentGrid lang="vi" phase={phase} />);
    const dimmed = container.querySelectorAll("[data-dim-wrapper].dimmed");
    expect(dimmed.length).toBeGreaterThan(0);
    dimmed.forEach((wrapper) => {
      // the class is on the WRAPPER, never on the card itself
      expect(wrapper.querySelector(".dimmed")).toBeNull();
      expect(Number(getComputedStyle(wrapper).opacity)).toBeLessThan(1);
    });
  });

  it("counts from the content, so adding a component is not a failure", () => {
    const phase = content.phases.phases[0].id;
    const expected = content.components.components
      .filter((c) => matchesPhase(c, phase)).length;
    render(<ComponentGrid lang="vi" phase={phase} />);
    expect(screen.getAllByRole("listitem", { current: true }).length)
      .toBe(expected);
  });

  it("lights a component the phase only runs through", () => {
    const traversed = content.components.components.find((c) =>
      c.phases.some((p) => p.relation === "traverses"));
    expect(traversed).toBeDefined();
    const phase = traversed!.phases.find((p) => p.relation === "traverses")!.id;
    expect(matchesPhase(traversed!, phase)).toBe(true);
  });

  it("counts ownership from creates and modifies only", () => {
    content.phases.phases.forEach((phase) => {
      const owners = content.components.components.filter((c) =>
        c.phases.some((p) => p.id === phase.id &&
          (p.relation === "creates" || p.relation === "modifies")));
      expect(owners.length).toBeGreaterThan(0);
    });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement**

```tsx
// Highlight on ANY relation. If only creates/modifies lit up, a phase's
// request would appear to stop dead at the components it calls but never
// changed.
export const matchesPhase = (component: Component, phase: string | null) =>
  phase === null || component.phases.some((p) => p.id === phase);
```

Grid markup — the dimming class goes on the wrapper, never the card:

```tsx
<li data-dim-wrapper className={lit ? undefined : "dimmed"} aria-current={lit}>
  <ComponentCard component={component} lang={lang} />
</li>
```

`styles.css`:

```css
[data-dim-wrapper] { transition: opacity 160ms ease; }
[data-dim-wrapper].dimmed { opacity: 0.28; }

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
```

- [ ] **Step 4: Run and see it pass**

- [ ] **Step 5: Prove it fails**

Move `className="dimmed"` from the `<li>` onto the card element and add `style={{opacity: 1}}` to the card — the first test fails on the "class is on the WRAPPER" assertion. This is the exact shape of the bug an animation library causes. Restore.

Then make `matchesPhase` ignore `traverses` → the third test fails. Restore.

- [ ] **Step 6: Commit**

```bash
git add docs-site
git commit -m "docs-site: layer 2 — the filter dims a parent, and a phase lights what it merely runs through"
```

---

### Task 12: Layer 3 — detail view, code, and GitHub deep links

**Files:**
- Create: `docs-site/src/views/ComponentDetail.tsx`, `docs-site/src/views/CodeExcerpt.tsx`, `docs-site/src/views/FlowDiagram.tsx`, `docs-site/src/github.ts`, `docs-site/tests/detail.test.tsx`

**Interfaces:**
- Consumes: `content.components/*`, `wrapLabel`, `laneOffsets`.
- Produces: `githubUrl(file, from, to) -> string`.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, expect, it } from "vitest";
import { githubUrl } from "../src/github";
import { render, screen } from "@testing-library/react";
import { ComponentDetail } from "../src/views/ComponentDetail";
import { content } from "../src/content";

describe("layer 3", () => {
  it("links to the exact lines on GitHub", () => {
    expect(githubUrl("tablerag/api/main.py", 34, 71)).toBe(
      "https://github.com/NgoHung0704/LedgerRAG/blob/main/tablerag/api/main.py#L34-L71");
    expect(githubUrl("tablerag/api/main.py", 34, 34)).toBe(
      "https://github.com/NgoHung0704/LedgerRAG/blob/main/tablerag/api/main.py#L34");
  });

  it("shows every function the content declares, with its file and line", () => {
    const id = content.components.components[0].id;
    render(<ComponentDetail id={id} lang="vi" />);
    const detail = content.componentDetails[id];
    detail.functions.forEach((fn: any) => {
      expect(screen.getByText(fn.decl)).toBeTruthy();
      expect(screen.getByText(`${fn.file}:${fn.line}`)).toBeTruthy();
    });
  });

  it("renders the debts, not only the good parts", () => {
    const withDebt = Object.values(content.componentDetails)
      .find((d: any) => (d.debts ?? []).length > 0) as any;
    render(<ComponentDetail id={withDebt.id} lang="vi" />);
    withDebt.debts.forEach((debt: any) => {
      expect(screen.getByText(debt.text.vi)).toBeTruthy();
    });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement `github.ts`**

```ts
const REPO = "https://github.com/NgoHung0704/LedgerRAG/blob/main";

export const githubUrl = (file: string, from: number, to: number): string =>
  `${REPO}/${file}#L${from}${to > from ? `-L${to}` : ""}`;
```

- [ ] **Step 4: Implement the detail view**

Sections in order: summary · flow diagram (same `wrapLabel`/`laneOffsets`, same text-version treatment as Task 10) · functions (`decl` in a `<code>`, `file:line` linking to GitHub) · code excerpts rendered from `cite.code` · why cards · debt cards. Debts get their own visual treatment and are never collapsed by default — a handover page that hides its debts is the failure mode this whole page exists to avoid.

- [ ] **Step 5: Run and see green**

- [ ] **Step 6: Prove it fails** — return a URL without the `#L` fragment → the link test fails. Skip rendering `debts` → the debt test fails. Restore.

- [ ] **Step 7: Commit**

```bash
git add docs-site
git commit -m "docs-site: layer 3 — functions, real code, deep links, and the debts shown next to them"
```

---

### Task 13: The assembly-line view

**Files:**
- Create: `docs-site/src/views/MachineDiagram.tsx`, `docs-site/tests/machine.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it("lights the parts of the filtered phase and dims the rest, via wrappers", () => {
  const machine = content.machines.machines[0];
  const phase = machine.parts.flatMap((p) => p.phases)[0];
  const { container } = render(<MachineDiagram id={machine.id} lang="vi" phase={phase} />);
  machine.parts.forEach((part) => {
    const wrapper = container.querySelector(`[data-part="${part.id}"]`)!;
    const lit = part.phases.includes(phase);
    expect(wrapper.classList.contains("dimmed")).toBe(!lit);
    expect(wrapper.querySelector(".dimmed")).toBeNull();
  });
});

it("names every exit and every gate in the text version", () => {
  const machine = content.machines.machines[0];
  render(<MachineDiagram id={machine.id} lang="vi" phase={null} />);
  const text = screen.getByTestId("diagram-text").textContent ?? "";
  machine.exits.forEach((exit) => expect(text).toContain(exit.label.vi));
  machine.edges.forEach((edge) => edge.label && expect(text).toContain(edge.label.vi));
});
```

- [ ] **Step 2: Run to verify it fails**
- [ ] **Step 3: Implement** — inlet on the left, parts as a chain, exits on the right; dimming class on the `<g data-part>` wrapper; reuse `wrapLabel`, `laneOffsets`, `DiagramText`.
- [ ] **Step 4: Run and see green**
- [ ] **Step 5: Prove it fails** — put the dim class on the inner rect instead of the wrapper → first test fails. Restore.
- [ ] **Step 6: Commit**

```bash
git add docs-site
git commit -m "docs-site: the assembly lines, with the phase filter lighting the parts it touches"
```

---

### Task 14: Wire the site into CI and Pages

**Files:**
- Modify: `.github/workflows/ci.yml`, `Makefile`

- [ ] **Step 1: Add the build and deploy jobs**

```yaml
  docs-site:
    needs: python-gates
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: docs-site } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: docs-site/package-lock.json
      - run: npm ci
      - name: Typecheck
        run: npx tsc --noEmit
      - name: Behaviour tests
        run: npx vitest run
      - name: Build
        run: npx vite build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: docs-site/dist

  deploy:
    needs: docs-site
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - id: deploy
        uses: actions/deploy-pages@v4
```

`needs: python-gates` is the point: a red guard means nothing reaches the web.

- [ ] **Step 2: Add Makefile targets**

```makefile
# ---- docs site ------------------------------------------------------------
docs-test:
	cd docs-site && npx vitest run

docs-build:
	cd docs-site && npx vite build
```

Add `docs-test docs-build docs-relink` to `.PHONY`.

- [ ] **Step 3: Verify the lockfile is tracked**

```powershell
git check-ignore -v docs-site/package-lock.json
Write-Output "IGNORED_EXIT=$LASTEXITCODE"
```

Expected: `IGNORED_EXIT=1` (not ignored). If it is ignored, `npm ci` cannot run in CI — fix `.gitignore` before continuing.

- [ ] **Step 4: Run every gate locally, bare**

```powershell
& ".venv\Scripts\python.exe" -m ruff check tablerag tests spike
Write-Output "RUFF_EXIT=$LASTEXITCODE"
& ".venv\Scripts\python.exe" -m pytest tests/unit -q
Write-Output "PYTEST_EXIT=$LASTEXITCODE"
Set-Location docs-site
npx tsc --noEmit
Write-Output "TSC_EXIT=$LASTEXITCODE"
npx vitest run
Write-Output "VITEST_EXIT=$LASTEXITCODE"
npx vite build
Write-Output "BUILD_EXIT=$LASTEXITCODE"
Set-Location ..
```

All five must be 0. Do not pipe any of them through `tail`.

- [ ] **Step 5: Commit and push**

```bash
git add .github/workflows/ci.yml Makefile docs-site/package-lock.json
git commit -m "ci: build and publish the architecture page, but only behind the guards"
git push
```

- [ ] **Step 6: Tell the user to flip the Pages source**

The deploy job cannot work until **Settings → Pages → Source** is changed from *Deploy from a branch* to **GitHub Actions**. Only the repository owner can do this. Report the first workflow run's URL and its result.

---

### Task 15: Acceptance

**Files:** none — this task produces evidence, not code.

- [ ] **Step 1: Re-prove every guard fails when its behaviour is broken**

Work through the break/restore list from Tasks 2–13 in one pass and record, per test, the failure message seen. Any test that cannot be made to fail is not a test — fix it or delete it.

- [ ] **Step 2: Run every gate bare, capturing exit codes**

The Step 4 block from Task 14. Record all five exit codes verbatim in the report.

- [ ] **Step 3: Look at the page**

```powershell
Set-Location docs-site
npm install -D playwright
npx playwright install chromium
Write-Output "PW_EXIT=$LASTEXITCODE"
```

If the browser download fails, **say so in the report and state plainly that the page was not opened.** Do not imply visual checking that did not happen.

If it succeeds, write `docs-site/tools/shots.mjs` to build, serve `dist`, and capture, for each of `map`, `grid`, one `c/<id>`, and one `machine/<id>`:

- 1440×900, `vi` and `en`
- 390×844, `vi` and `en`
- 1440×900 with `reducedMotion: "reduce"`

Then read each PNG and check for: SVG text crossing its box, edges overlapping labels, labels colliding, low-contrast text, and horizontal overflow at 390px.

- [ ] **Step 4: Check the language switch leaves nothing behind**

With the page in `en`, assert no Vietnamese-specific letter appears in `document.body.innerText`, and the reverse for `vi` against a marker English string. Run it in Playwright over every view.

- [ ] **Step 5: Write the report**

State: every gate's exit code; which tests were seen red and how; what the screenshots showed and what was fixed; whether the page was opened at all; and what remains outstanding. If anything was skipped, say which and why.

- [ ] **Step 6: Commit any fixes the screenshots forced**

```bash
git add -A
git commit -m "docs-site: fixes found by looking at the rendered page"
```

---

## Self-Review

**Spec coverage:** §1 goal → Tasks 7, 12 (debts rendered). §2 findings → Task 1 (CI/ruff), Global Constraints (CRLF). §3 decisions → all tasks. §4 architecture → Task 9. §5 content model → Tasks 2, 3, 7. §6 three layers → Tasks 10, 11, 12; machines → Tasks 8, 13. §7 component mapping → Task 6 Step 3. §8 guards G0–G9 → Tasks 2 (G5, G8, shape), 3 (G1, G2), 4 (G4), 5 (G7), 6 (G3, G6), 9 (G9). §8.1 definitions → the test code in those tasks. §9 ruff → Task 1. §10 interaction/a11y → Tasks 9, 10, 11. §11 Vitest list → Tasks 9 (2, 3), 10 (4, 5, 6), 11 (1). §12 CI/deploy → Tasks 1, 14. §13 acceptance → Task 15. §14 out of scope → not implemented, as intended. §15 order → task order, with each task ending green rather than staging a deliberate red, which is strictly better.

**Placeholder scan:** No TBD/TODO. Content-authoring steps (Tasks 3–8) name the exact source to read and the exact shape to produce rather than shipping 21 files of prose inside the plan; the guards define completion, so "done" is machine-checkable rather than a matter of taste.

**Type consistency:** `pick(value, lang)` used in Tasks 9–13. `matchesPhase(component, phase)` defined and used in Task 11 only. `wrapLabel`/`boxHeight`/`laneOffsets`/`columnGap` defined in Task 10, reused in Tasks 12, 13. `githubUrl(file, from, to)` defined in Task 12. `popOne`/`parseRoute`/`formatRoute`/`navigate` defined in Task 9. `source_endpoints`/`source_stores`/`source_modules`/`load_components` all defined in `docs_guard_lib.py` before first use. `citation.decl` introduced in the content shapes section and guarded in Task 7.

**One gap found and closed:** the spec's §11 test 3 ("language switch leaves no trace of the other language") is a DOM-wide property that jsdom checks poorly, so it appears twice — as content guard G8 in Task 2, and as a Playwright assertion over the real rendered page in Task 15 Step 4.
