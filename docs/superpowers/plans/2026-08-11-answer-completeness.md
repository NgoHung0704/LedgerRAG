# Answer Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make answers complete and honestly hedged — pull in the neighbouring
context a chunk needs, say when two sources cover the same subject differently,
and flag when an answer rests on a model's reading of a picture.

**Architecture:** Three additions to the query pipeline, under one shared budget.
A new `ExpandNeighbours` step runs between `Rerank` and `AssembleContext`.
`AssembleContext` gains a deterministic total character budget with a fixed
sacrifice order. A pure `overlap.py` module groups same-subject sources and
`generate.py` gains a conditional rule telling the model to contrast rather than
merge them. The caution is a structured response field computed after
generation, never prose inside the answer.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy (PostgreSQL JSONB), pytest,
Next.js 14 + Tailwind frontend.

## Global Constraints

- **No migrations.** `Base.metadata.create_all` adds TABLES, never COLUMNS. Any
  new per-KB setting goes into the existing `KnowledgeBase.config` JSONB dict.
- **A feature must never fail an answer.** Expansion, overlap detection and
  caution computation each degrade to "off" on exception, and log. The answer
  still goes out.
- **`SYSTEM_PROMPT` is the measured configuration.** New prompt text is appended
  conditionally (the `FIGURE_RULE` pattern) so a query without the triggering
  condition stays byte-identical.
- **Prove the test fails first.** Every task runs the new test and sees it red
  before the implementation exists.
- `CHARS_PER_TOKEN = 3.0` — deliberately under French's real ~3.5-4.
- `reserve_tokens = 3000` — system prompt (~1200 with both conditional rules)
  plus room for the answer.
- `TABLE_HTML_LIMIT`: 12000 -> 24000. `chat_num_ctx`: 16384 -> 32768.
- Reading order is `(page, bbox[1], bbox[0])`. `Element.bbox` is `[x0,y0,x1,y1]`.
- Run tests with `python -m pytest tests/unit -q` from the repo root.

---

### Task 1: Assembly budget

**Files:**
- Modify: `tablerag/query/steps/assemble.py:29-35` (limits), `:80-101` (run)
- Modify: `tablerag/core/config.py:141` (`chat_num_ctx`), add `context_reserve_tokens`
- Test: `tests/unit/test_assemble_budget.py`

**Interfaces:**
- Consumes: `SourceBlock` from `tablerag.query.pipeline`
- Produces: `trim_to_budget(blocks: list[SourceBlock], budget_chars: int) -> tuple[list[SourceBlock], list[str]]`
  returning kept blocks and human-readable descriptions of what was dropped or
  truncated. `budget_chars(settings) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_assemble_budget.py
import uuid

from tablerag.query.pipeline import SourceBlock
from tablerag.query.steps.assemble import budget_chars, trim_to_budget


def _block(content: str, expanded: bool = False) -> SourceBlock:
    return SourceBlock(
        kind="text", doc_id=uuid.uuid4(), filename="notice.pdf", page=1,
        element_id=uuid.uuid4(), chunk_id=uuid.uuid4(), content=content,
        snippet=content[:240], score=0.5, crop_image_path="c.png",
        confidence=1.0, expanded=expanded)


def test_under_budget_keeps_everything():
    blocks = [_block("a" * 100), _block("b" * 100)]
    kept, dropped = trim_to_budget(blocks, 1000)
    assert kept == blocks
    assert dropped == []


def test_expansions_are_sacrificed_before_primary_sources():
    primary_a, primary_b = _block("a" * 100), _block("b" * 100)
    extra = _block("c" * 100, expanded=True)
    kept, dropped = trim_to_budget([primary_a, primary_b, extra], 250)
    assert kept == [primary_a, primary_b]
    assert len(dropped) == 1


def test_an_expanded_block_goes_before_a_lower_ranked_primary():
    # the expanded one sits in the MIDDLE on purpose: with it last, a function
    # that merely pops the tail passes this test without honouring `expanded`
    top = _block("a" * 100)
    extra = _block("b" * 100, expanded=True)
    primary_low = _block("c" * 100)
    kept, dropped = trim_to_budget([top, extra, primary_low], 250)
    assert kept == [top, primary_low]
    assert "(expanded)" in dropped[0]


def test_budget_chars_leaves_room_for_the_prompt_and_the_answer():
    class _Settings:
        chat_num_ctx = 32768
        context_reserve_tokens = 3000

    assert budget_chars(_Settings()) == int((32768 - 3000) * 3.0)


def test_the_top_ranked_source_is_never_dropped():
    blocks = [_block("a" * 500), _block("b" * 500)]
    kept, dropped = trim_to_budget(blocks, 10)
    assert len(kept) == 1
    assert kept[0] is blocks[0]
    # it does not fit either, so it was truncated rather than dropped
    assert len(kept[0].content) <= 10
    assert dropped


def test_truncation_happens_only_after_dropping_is_exhausted():
    keep, drop = _block("a" * 200), _block("b" * 200)
    kept, _ = trim_to_budget([keep, drop], 200)
    assert len(kept) == 1
    assert kept[0].content == "a" * 200  # untouched: dropping was enough
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_assemble_budget.py -q`
Expected: FAIL — `ImportError: cannot import name 'trim_to_budget'` (and
`SourceBlock` has no `expanded` field yet).

- [ ] **Step 3: Add the `expanded` field to `SourceBlock`**

In `tablerag/query/pipeline.py`, after `from_figure: bool = False`:

```python
    # pulled in because it neighbours a retrieved source, not because it was
    # retrieved. Kept separable so a reader can still see what search found.
    expanded: bool = False
```

- [ ] **Step 4: Implement the budget in `assemble.py`**

Replace the limits block at `tablerag/query/steps/assemble.py:29-35`:

```python
SNIPPET_CHARS = 240
# must hold a full multi-page merged table: truncating mid-table silently
# amputates the later rows (the Glossaire cross-page table is ~2x the old
# 6000 limit). Budgeted against chat_num_ctx=32768.
TABLE_HTML_LIMIT = 24000
# how many matched rows to surface above a table before it becomes noise again
MAX_MATCHED_ROWS = 4
# Under French's real ~3.5-4 chars/token on purpose: the cost of guessing low
# is a slightly smaller context, the cost of guessing high is that Ollama
# truncates from the TOP of the prompt and silently deletes every safety rule
# in SYSTEM_PROMPT (config.py:137). Asymmetric, so err low.
CHARS_PER_TOKEN = 3.0


def budget_chars(settings) -> int:
    """How many characters of sources fit, leaving room for prompt and answer."""
    usable = max(settings.chat_num_ctx - settings.context_reserve_tokens, 0)
    return int(usable * CHARS_PER_TOKEN)


def trim_to_budget(blocks: list[SourceBlock], budget: int
                   ) -> tuple[list[SourceBlock], list[str]]:
    """Fit the sources into `budget` characters, sacrificing in a fixed order.

    The victim is the lowest-ranked EXPANDED block when there is one, and the
    lowest-ranked primary source otherwise. That choice is made HERE rather than
    inherited from the caller's ordering: "neighbours are sacrificed first" is
    what this function promises, and a promise defended only by how another file
    happens to sort its input is not defended at all. Surviving blocks keep
    their original order, so citation numbering does not shift.

    The top-ranked source is never dropped — if it alone exceeds the budget it
    is truncated, because returning nothing is worse than returning a shortened
    best source.

    Returns the kept blocks and a description of every sacrifice, so the caller
    can log what the user did not get to see.
    """
    dropped: list[str] = []
    kept = list(blocks)

    def total() -> int:
        return sum(len(b.content) for b in kept)

    while len(kept) > 1 and total() > budget:
        # range starts at 1: index 0 is the top-ranked source and is structurally
        # ineligible. (expanded, index) picks expanded over primary, and the
        # lowest rank within whichever group is chosen.
        victim = max(range(1, len(kept)), key=lambda i: (kept[i].expanded, i))
        gone = kept.pop(victim)
        dropped.append(f"dropped {gone.kind} {gone.filename} p{gone.page}"
                       f"{' (expanded)' if gone.expanded else ''}")
    if kept and total() > budget:
        head = kept[0]
        dropped.append(f"truncated {head.kind} {head.filename} p{head.page} "
                       f"from {len(head.content)} to {budget} chars")
        head.content = head.content[:budget]
    return kept, dropped
```

- [ ] **Step 5: Add `context_reserve_tokens` and raise `chat_num_ctx`**

In `tablerag/core/config.py`, change `chat_num_ctx: int = 16384` to `32768` and
add directly beneath it:

```python
    # held back from chat_num_ctx for the system prompt and the answer itself,
    # so assembled sources can never push SYSTEM_PROMPT off the top
    context_reserve_tokens: int = 3000
```

- [ ] **Step 6: Wire it into `AssembleContext.run`**

In `tablerag/query/steps/assemble.py`, replace `ctx.sources = blocks` (around
line 92) with:

```python
        from tablerag.core.config import get_settings

        blocks, sacrificed = trim_to_budget(blocks, budget_chars(get_settings()))
        if sacrificed:
            # the one moment a user is at risk of an incomplete answer through
            # no fault of retrieval — it must be visible in the logs
            logger.warning("context budget exceeded, sacrificed: %s",
                           "; ".join(sacrificed))
        ctx.sources = blocks
```

Add at the top of the file, after the existing imports:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 7: Run the tests**

Run: `python -m pytest tests/unit -q`
Expected: PASS, including the whole existing suite (881 tests before this task).

- [ ] **Step 8: Commit**

```bash
git add tablerag/query/steps/assemble.py tablerag/query/pipeline.py \
        tablerag/core/config.py tests/unit/test_assemble_budget.py
git commit -m "we choose what gets cut, instead of Ollama cutting the safety rules"
```

---

### Task 2: Overlap detection (pure module)

**Files:**
- Create: `tablerag/query/overlap.py`
- Test: `tests/unit/test_overlap.py`

**Interfaces:**
- Consumes: nothing (pure; takes strings and `SourceBlock`s)
- Produces:
  - `header_signature(html: str) -> str | None`
  - `subject_signature(text: str) -> frozenset[str]`
  - `jaccard(a: frozenset[str], b: frozenset[str]) -> float`
  - `group_overlapping(blocks: list[SourceBlock], threshold: float = 0.5) -> list[list[int]]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_overlap.py
import uuid

from tablerag.query.overlap import (
    group_overlapping,
    header_signature,
    jaccard,
    subject_signature,
)
from tablerag.query.pipeline import SourceBlock

SIBLING_A = "<table><tr><th>Garantie</th><th>Niveau 1</th></tr>" \
            "<tr><td>Optique</td><td>100 %</td></tr></table>"
SIBLING_B = "<table><tr><th>Garantie</th><th>Niveau 1</th></tr>" \
            "<tr><td>Optique</td><td>150 %</td></tr></table>"
OTHER = "<table><tr><th>Échelon</th><th>Salaire</th></tr>" \
        "<tr><td>3</td><td>34 900</td></tr></table>"


def _table(html: str, filename: str) -> SourceBlock:
    return SourceBlock(
        kind="table", doc_id=uuid.uuid4(), filename=filename, page=3,
        element_id=uuid.uuid4(), content=html, snippet="", score=0.5,
        crop_image_path="c.png")


def test_same_headers_different_numbers_share_a_signature():
    assert header_signature(SIBLING_A) == header_signature(SIBLING_B)


def test_different_headers_do_not():
    assert header_signature(SIBLING_A) != header_signature(OTHER)


def test_a_table_with_no_header_row_has_no_signature():
    assert header_signature("<table><tr><td>7</td></tr></table>") is None


def test_boilerplate_alone_does_not_make_two_chunks_the_same_subject():
    # the words every French notice repeats; nothing specific is shared
    a = subject_signature("Le présent document est remis à chaque salarié "
                          "de l'entreprise conformément aux dispositions.")
    b = subject_signature("Le présent document est remis à chaque salarié "
                          "de l'entreprise conformément aux dispositions.")
    # identical text does overlap - that is correct - but the rare terms
    # carrying the subject must be what drives it
    assert jaccard(a, b) == 1.0
    c = subject_signature("Le présent document est remis à chaque salarié "
                          "conformément au régime de prévoyance obligatoire.")
    d = subject_signature("Le présent document est remis à chaque salarié "
                          "conformément au barème des indemnités kilométriques.")
    assert jaccard(c, d) < 0.5


def test_groups_two_sibling_tables_and_leaves_the_third_alone():
    blocks = [_table(SIBLING_A, "notice-2024.pdf"),
              _table(OTHER, "grille.pdf"),
              _table(SIBLING_B, "notice-2025.pdf")]
    assert group_overlapping(blocks) == [[0, 2]]


def test_no_groups_when_nothing_overlaps():
    assert group_overlapping([_table(OTHER, "grille.pdf")]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_overlap.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tablerag.query.overlap'`

- [ ] **Step 3: Write the module**

```python
# tablerag/query/overlap.py
"""Which retrieved sources are covering the SAME subject as each other.

A corpus of insurance notices and HR grids is full of tables that share a
structure and differ only in their numbers: the 2024 guarantee table and the
2025 one, the technical department's scale and the administrative one. Both are
retrieved, both look right, and an answer that merges them is wrong in a way
nobody can see.

What is computed here is deliberately shallow: WHICH sources belong together,
never WHAT they say differently. The second question needs the meaning of the
text, which is the model's job — a machine-made claim about it would be a
fabrication sitting inside the context window, which is the worst place for one.

Two signatures, because the two kinds of source fail differently:

  - tables: their header row. Siblings share it exactly; unrelated tables do
    not. No threshold, no tuning.
  - text: the RARE words. Jaccard over every word groups any two paragraphs of
    French administrative prose, because they all repeat the same hundred
    words; dropping those leaves what the passage is actually about.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# the words a French (and English) document repeats on every page: they say
# nothing about which subject a passage covers
_STOPWORDS = frozenset("""
au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma
mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se
ses son sur ta te tes toi ton tu un une vos votre vous est sont etre a ils
plus tout tous toute toutes autre autres cas selon dont ainsi entre sans
present presente document salarie salaries entreprise conformement dispositions
the of and to in for is are be as by or an at this that with from it its on
""".split())

_TAG = re.compile(r"<[^>]+>")
_HEADER_CELL = re.compile(r"<th\b[^>]*>(.*?)</th>", re.I | re.S)
_WORD = re.compile(r"[a-zA-Zà-öø-ÿ]{3,}")


def _fold(text: str) -> str:
    """Lowercase, strip accents and anything that is not a letter."""
    stripped = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return re.sub(r"[^a-z]+", "", stripped.lower())


def header_signature(html: str) -> str | None:
    """A hash of the table's header cells, or None when it has no header.

    Digits are folded out with everything else, so the 2024 table and the 2025
    table hash the same — which is the entire point: they ARE the same table,
    filled in at two moments."""
    cells = [_fold(_TAG.sub(" ", cell)) for cell in _HEADER_CELL.findall(html)]
    cells = [c for c in cells if c]
    if not cells:
        return None
    joined = "|".join(sorted(cells))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def subject_signature(text: str) -> frozenset[str]:
    """The rare content words of a passage — what it is ABOUT."""
    words = {_fold(w) for w in _WORD.findall(text)}
    return frozenset(w for w in words if w and w not in _STOPWORDS)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def group_overlapping(blocks, threshold: float = 0.5) -> list[list[int]]:
    """Indices of blocks covering the same subject, as groups of 2 or more.

    `threshold` is a starting value, NOT a measured one. It must be set from
    the corpus before this is trusted — see the plan's measurement task."""
    groups: list[list[int]] = []
    used: set[int] = set()
    signatures = [header_signature(b.content) if b.kind == "table"
                  else subject_signature(b.content) for b in blocks]
    for i, sig_i in enumerate(signatures):
        if i in used or not sig_i:
            continue
        group = [i]
        for j in range(i + 1, len(blocks)):
            sig_j = signatures[j]
            if j in used or not sig_j or blocks[i].kind != blocks[j].kind:
                continue
            same = (sig_i == sig_j if blocks[i].kind == "table"
                    else jaccard(sig_i, sig_j) >= threshold)
            if same:
                group.append(j)
        if len(group) > 1:
            groups.append(group)
            used.update(group)
    return groups
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_overlap.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add tablerag/query/overlap.py tests/unit/test_overlap.py
git commit -m "which sources cover the same subject - not what they say differently"
```

---

### Task 3: Overlap note and the conditional contrast rule

**Files:**
- Modify: `tablerag/query/steps/generate.py:88-112`
- Modify: `tablerag/query/steps/assemble.py` (build the note)
- Test: `tests/unit/test_overlap_note.py`

**Interfaces:**
- Consumes: `group_overlapping` from Task 2, `SourceBlock.expanded` from Task 1
- Produces: `overlap_note(blocks, groups) -> str` in `tablerag/query/overlap.py`;
  `build_system_prompt(..., has_overlap: bool = False)` in `generate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_overlap_note.py
import uuid

from tablerag.query.overlap import overlap_note, period_of
from tablerag.query.pipeline import SourceBlock
from tablerag.query.steps.generate import OVERLAP_RULE, build_system_prompt


def _table(filename: str, context: str = "") -> SourceBlock:
    return SourceBlock(
        kind="table", doc_id=uuid.uuid4(), filename=filename, page=3,
        element_id=uuid.uuid4(), content="<table></table>", snippet="",
        score=0.5, crop_image_path="c.png", context=context)


def test_period_is_read_from_a_year_or_a_quarter():
    assert period_of("Notice 2024.pdf", "") == "2024"
    assert period_of("notice.pdf", "Résultats T1") == "T1"
    assert period_of("notice.pdf", "Garanties") is None


def test_the_note_names_each_source_by_number_and_provenance():
    blocks = [_table("notice-2024.pdf", "Garanties optique"),
              _table("notice-2025.pdf", "Garanties optique")]
    note = overlap_note(blocks, [[0, 1]])
    assert "[1]" in note and "[2]" in note
    assert "notice-2024.pdf" in note and "notice-2025.pdf" in note
    assert "Garanties optique" in note


def test_no_groups_means_no_note():
    assert overlap_note([_table("a.pdf")], []) == ""


def test_the_contrast_rule_is_absent_unless_there_is_an_overlap():
    assert OVERLAP_RULE not in build_system_prompt()
    assert OVERLAP_RULE in build_system_prompt(has_overlap=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_overlap_note.py -q`
Expected: FAIL — `ImportError: cannot import name 'overlap_note'`

- [ ] **Step 3: Add `context` to `SourceBlock`**

In `tablerag/query/pipeline.py`, beside `expanded`:

```python
    # the heading printed above this element (Element.meta["context"]), which is
    # often the only place a period or department is written down
    context: str = ""
```

Populate it in `assemble.py` — `_text_block` and `_table_block` both gain
`context=...` from the hydrated row. `ChunkContext` and `TableSource` in
`tablerag/storage/repositories.py` each gain `context: str = ""`, filled from
`Element.meta.get("context", "")` in `get_chunk_contexts` and
`get_table_sources`.

- [ ] **Step 4: Add `period_of` and `overlap_note` to `overlap.py`**

```python
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_QUARTER = re.compile(r"\b([TQ][1-4])\b", re.I)


def period_of(filename: str, context: str) -> str | None:
    """A year or a quarter, if one is written in the heading or the filename.

    Nothing cleverer on purpose. This is the difference we can PROVE is there;
    inferring a period from prose would be a guess presented as provenance."""
    for text in (context, filename):
        if match := _QUARTER.search(text or ""):
            return match.group(1).upper()
        if match := _YEAR.search(text or ""):
            return match.group(0)
    return None


def overlap_note(blocks, groups: list[list[int]]) -> str:
    """One line per group, naming what provably differs between its members."""
    if not groups:
        return ""
    lines = []
    for group in groups:
        kind = blocks[group[0]].kind
        lines.append(f"These sources are the same kind of {kind}, "
                     f"from different places:")
        for i in group:
            block = blocks[i]
            where = [block.filename, f"p{block.page}"]
            if period := period_of(block.filename, block.context):
                where.append(period)
            if block.context:
                where.append(f"« {block.context} »")
            lines.append(f"  [{i + 1}] " + " · ".join(where))
    return "\n".join(lines)
```

- [ ] **Step 5: Add the conditional rule to `generate.py`**

After `FIGURE_RULE` in `tablerag/query/steps/generate.py`:

```python
# Appended only when two or more sources were detected as covering the same
# subject. Conditional for the same reason FIGURE_RULE is: a query with no
# look-alikes must keep the answering prompt byte-identical to the measured
# configuration.
OVERLAP_RULE = """
- Some sources are marked as covering THE SAME SUBJECT from different places. \
Never merge them into a single statement. Give each version with its own \
citation and say which document (and period, if stated) it comes from. If they \
disagree, say plainly that they disagree. If the question does not name a \
document or a period, do NOT choose one for the user — give both, attributed.\
"""
```

Change the signature and body of `build_system_prompt`:

```python
def build_system_prompt(extra_instructions: str = "", identity: str = "",
                        has_figures: bool = False,
                        has_overlap: bool = False) -> str:
```

and after the `has_figures` branch:

```python
    if has_overlap:
        prompt += OVERLAP_RULE
```

- [ ] **Step 6: Pass the note and the flag through `GenerateAnswer`**

Where `GenerateAnswer` builds its prompt, compute the groups once and use both:

```python
        try:
            groups = group_overlapping(ctx.sources)
            note = overlap_note(ctx.sources, groups)
        except Exception:  # noqa: BLE001 — an answer must survive this
            logger.exception("overlap detection failed (non-fatal)")
            groups, note = [], ""
        system = build_system_prompt(
            ctx.extra_instructions, ctx.identity,
            has_figures=any(b.from_figure for b in ctx.sources),
            has_overlap=bool(groups))
```

and prepend `note` (when non-empty) to the assembled context block, separated by
a blank line. Add `logger = logging.getLogger(__name__)` at the top of
`generate.py` if it is not already there.

Failure here degrades to "no note, no rule", which is exactly today's behaviour
— the global constraint that a feature never fails an answer.

- [ ] **Step 7: Run the tests**

Run: `python -m pytest tests/unit -q`
Expected: PASS. `tests/unit/test_generate.py` must still pass unchanged — if it
does not, the prompt moved for a query with no overlap, which the design forbids.

- [ ] **Step 8: Commit**

```bash
git add tablerag/query/overlap.py tablerag/query/steps/generate.py \
        tablerag/query/steps/assemble.py tablerag/query/pipeline.py \
        tablerag/storage/repositories.py tests/unit/test_overlap_note.py
git commit -m "point at the look-alikes instead of hoping the model notices"
```

---

### Task 4: Reading-order neighbour selection

**Files:**
- Create: `tablerag/query/neighbours.py`
- Modify: `tablerag/storage/repositories.py` (fetch)
- Test: `tests/unit/test_neighbours.py`

**Interfaces:**
- Consumes: nothing pure; the repository call takes `list[uuid.UUID]`
- Produces:
  - `NeighbourCandidate` dataclass: `element_id, doc_id, page, y, x, type`
  - `choose_neighbours(candidates, winners) -> list[uuid.UUID]`
  - `get_page_elements(s, doc_ids) -> list[NeighbourCandidate]` in repositories

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_neighbours.py
import uuid

from tablerag.query.neighbours import NeighbourCandidate, choose_neighbours

DOC = uuid.uuid4()


def _c(page: int, y: float, type_: str = "text") -> NeighbourCandidate:
    return NeighbourCandidate(element_id=uuid.uuid4(), doc_id=DOC, page=page,
                              y=y, x=0.0, type=type_)


def test_a_text_winner_takes_the_element_before_and_after_it():
    a, b, c = _c(1, 100), _c(1, 200), _c(1, 300)
    picked = choose_neighbours([a, b, c], [b.element_id])
    assert set(picked) == {a.element_id, c.element_id}


def test_a_table_pulls_no_neighbours_of_its_own():
    a, table, c = _c(1, 100), _c(1, 200, "table"), _c(1, 300)
    assert choose_neighbours([a, table, c], [table.element_id]) == []


def test_every_table_and_figure_on_the_winner_s_page_comes_along():
    text = _c(2, 100)
    table = _c(2, 400, "table")
    figure = _c(2, 600, "figure")
    elsewhere = _c(3, 100, "table")
    picked = choose_neighbours([text, table, figure, elsewhere],
                               [text.element_id])
    assert table.element_id in picked and figure.element_id in picked
    assert elsewhere.element_id not in picked


def test_a_winner_is_never_returned_as_its_own_neighbour():
    a, b = _c(1, 100), _c(1, 200)
    picked = choose_neighbours([a, b], [a.element_id, b.element_id])
    assert picked == []


def test_reading_order_crosses_pages_but_never_documents():
    other_doc = NeighbourCandidate(element_id=uuid.uuid4(), doc_id=uuid.uuid4(),
                                   page=1, y=150, x=0.0, type="text")
    a, b = _c(1, 100), _c(1, 200)
    picked = choose_neighbours([a, b, other_doc], [b.element_id])
    assert other_doc.element_id not in picked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_neighbours.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tablerag.query.neighbours'`

- [ ] **Step 3: Write the module**

```python
# tablerag/query/neighbours.py
"""What a retrieved chunk needs around it in order to mean anything.

Retrieval matches a chunk because it holds the keyword. But a paragraph that
leads INTO the answer, and the one that continues it, hold no keyword at all —
they are the sentences either side, and they are why the matched one is
readable. The same is true of the table or the chart the prose is describing:
they are on the page, they are the point, and no word in them was searched for.

Two rules, and the second is a fence rather than a feature:

  - a text winner takes the element immediately before and after it in reading
    order, within its own document.
  - any winner takes the tables and figures on its own page.

Tables and figures take NOTHING. Without that, a table pulls its page, whose
text pulls its own neighbours, whose pages pull more tables, and one match
drags in a chapter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class NeighbourCandidate:
    element_id: uuid.UUID
    doc_id: uuid.UUID
    page: int
    y: float
    x: float
    type: str  # 'text' | 'table' | 'figure'


def choose_neighbours(candidates: list[NeighbourCandidate],
                      winners: list[uuid.UUID]) -> list[uuid.UUID]:
    """Element ids to pull in beside the winners, in reading order, no repeats."""
    won = set(winners)
    ordered = sorted(candidates, key=lambda c: (c.doc_id.int, c.page, c.y, c.x))
    by_id = {c.element_id: c for c in ordered}
    picked: list[uuid.UUID] = []

    def take(element_id: uuid.UUID) -> None:
        if element_id not in won and element_id not in picked:
            picked.append(element_id)

    for index, candidate in enumerate(ordered):
        if candidate.element_id not in won:
            continue
        if candidate.type == "text":
            for step in (-1, 1):
                near = index + step
                if 0 <= near < len(ordered) \
                        and ordered[near].doc_id == candidate.doc_id:
                    take(ordered[near].element_id)
        for other in ordered:
            if (other.doc_id == candidate.doc_id
                    and other.page == candidate.page
                    and other.type in ("table", "figure")):
                take(other.element_id)
    return [element_id for element_id in picked if element_id in by_id]
```

- [ ] **Step 4: Add the repository fetch**

In `tablerag/storage/repositories.py`, beside `get_chunk_contexts`:

```python
def get_page_elements(s: Session, doc_ids: list[uuid.UUID]
                      ) -> list["NeighbourCandidate"]:
    """Every element of these documents, as neighbour candidates.

    Whole documents rather than a page window: reading order is only correct
    when nothing is missing from it, and a document's element rows are small."""
    from tablerag.query.neighbours import NeighbourCandidate

    if not doc_ids:
        return []
    rows = s.query(Element).filter(Element.doc_id.in_(doc_ids)).all()
    return [NeighbourCandidate(
        element_id=row.id, doc_id=row.doc_id, page=row.page,
        y=float((row.bbox or [0, 0, 0, 0])[1]),
        x=float((row.bbox or [0, 0, 0, 0])[0]), type=row.type)
        for row in rows]
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/unit/test_neighbours.py -q`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add tablerag/query/neighbours.py tablerag/storage/repositories.py \
        tests/unit/test_neighbours.py
git commit -m "the sentences either side of the one that matched"
```

---

### Task 5: The ExpandNeighbours step

**Files:**
- Create: `tablerag/query/steps/expand.py`
- Modify: `tablerag/query/pipeline.py:142-150` (`default_pipeline`)
- Modify: `tablerag/core/config.py` (flag)
- Test: `tests/unit/test_expand_step.py`

**Interfaces:**
- Consumes: `choose_neighbours`, `get_page_elements` (Task 4); `SearchHit`
- Produces: `ExpandNeighbours` step class with `run(ctx) -> QueryContext`,
  appending synthetic hits carrying `payload["_expanded"] = True`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_expand_step.py
import uuid

import pytest

from tablerag.query.pipeline import QueryContext
from tablerag.query.steps.expand import ExpandNeighbours


class Boom:
    def __call__(self, *args, **kwargs):
        raise RuntimeError("database is down")


@pytest.mark.asyncio
async def test_expansion_failure_never_fails_the_query(monkeypatch):
    monkeypatch.setattr("tablerag.query.steps.expand.get_page_elements", Boom())
    ctx = QueryContext(kb_id=uuid.uuid4(), question="combien ?")
    ctx.hits = []
    out = await ExpandNeighbours(enabled=True).run(ctx)
    assert out.hits == []


@pytest.mark.asyncio
async def test_disabled_step_is_a_passthrough():
    ctx = QueryContext(kb_id=uuid.uuid4(), question="combien ?")
    ctx.hits = []
    assert await ExpandNeighbours(enabled=False).run(ctx) is ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_expand_step.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tablerag.query.steps.expand'`

- [ ] **Step 3: Write the step**

```python
# tablerag/query/steps/expand.py
"""Pull in the elements a retrieved source needs in order to be readable.

Placed AFTER Rerank so it cannot dilute ranking — the reranker judges what
search found, not what we then decided to bring along — and BEFORE
AssembleContext so everything it adds is subject to the same character budget
and is sacrificed first when that budget binds.

Expanded items are appended after the ranked hits and marked, so they take
their own citation numbers. Folding them into the winning source instead would
keep citation counts stable and make a fact from page 6 cite page 5; the
traceability principle is not worth a quieter gate.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from tablerag.query.neighbours import choose_neighbours
from tablerag.query.pipeline import QueryContext
from tablerag.storage.db import session_scope
from tablerag.storage.repositories import get_page_elements

logger = logging.getLogger(__name__)


class ExpandNeighbours:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    async def run(self, ctx: QueryContext) -> QueryContext:
        if not self.enabled or not ctx.hits:
            return ctx
        try:
            ctx.hits = ctx.hits + await asyncio.to_thread(self._extra, ctx.hits)
        except Exception:  # noqa: BLE001 — an answer must survive this
            logger.exception("neighbour expansion failed (non-fatal)")
        return ctx

    @staticmethod
    def _extra(hits: list) -> list:
        doc_ids, winners = set(), []
        for hit in hits:
            if raw := hit.payload.get("doc_id"):
                doc_ids.add(uuid.UUID(raw))
            if raw := hit.payload.get("element_id"):
                winners.append(uuid.UUID(raw))
        if not winners:
            return []
        with session_scope() as s:
            candidates = get_page_elements(s, sorted(doc_ids, key=str))
        by_id = {c.element_id: c for c in candidates}
        extra = []
        for element_id in choose_neighbours(candidates, winners):
            candidate = by_id[element_id]
            extra.append(type(hits[0])(
                id=element_id, score=0.0,
                payload={"element_id": str(element_id),
                         "doc_id": str(candidate.doc_id),
                         # assemble routes on this: a table element hydrates to
                         # its parent table, a text or figure element to its
                         # chunks. Without it every expansion would be looked up
                         # as a table and text neighbours would silently vanish.
                         "element_type": candidate.type,
                         "_collection": "expanded", "_expanded": True}))
        return extra
```

- [ ] **Step 4: Add the flag and wire the step in**

In `tablerag/core/config.py`, beside `retrieve_top_k`:

```python
    # off until measured: expansion changes citation counts, so eval-qa must be
    # re-run A/B before it can become the default (see the plan's last task)
    expand_neighbours: bool = False
```

In `tablerag/query/pipeline.py`, import `ExpandNeighbours` in `default_pipeline`
and insert it between `Rerank(...)` and `AssembleContext()`:

```python
        ExpandNeighbours(enabled=settings.expand_neighbours),
```

- [ ] **Step 5: Teach `AssembleContext` to hydrate and mark expanded hits**

`AssembleContext`'s hit loop currently sends anything that is not a chunk hit
down the table path. An expanded **text or figure** element has no parent table,
so without routing it would be looked up as a table and disappear. Add to
`tablerag/storage/repositories.py`:

```python
def get_element_chunk_contexts(s: Session, element_ids: list[uuid.UUID]
                               ) -> list[ChunkContext]:
    """The chunks of these elements — expansion arrives by element, not chunk."""
    if not element_ids:
        return []
    chunk_ids = [row.id for row in s.query(Chunk.id).filter(
        Chunk.element_id.in_(element_ids)).all()]
    return get_chunk_contexts(s, chunk_ids)
```

In `assemble.py`, before the existing hit loop, collect the expanded ids and
split them by type:

```python
        expanded_ids = {uuid.UUID(h.payload["element_id"])
                        for h in ctx.hits
                        if h.payload.get("_expanded")
                        and h.payload.get("element_id")}
        expanded_elements = [uuid.UUID(h.payload["element_id"])
                             for h in ctx.hits
                             if h.payload.get("_expanded")
                             and h.payload.get("element_type") != "table"]
```

Route table-typed expansions into `table_ids` as usual, fetch
`expanded_elements` through `get_element_chunk_contexts`, and set
`expanded=<id> in expanded_ids` on every block built from them.

- [ ] **Step 5b: Carry the flag onto the `Citation`**

`Citation` gains `expanded` in Task 6, but the citation list is built here. Add
`expanded=b.expanded` to the `Citation(...)` construction in
`AssembleContext.run` (around `assemble.py:93`). Without this the field exists,
is always `False`, and the frontend tag in Task 8 never appears — a whole
feature silently dead.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/unit -q`
Expected: PASS. With `expand_neighbours=False` by default, every existing
pipeline test must be unaffected.

- [ ] **Step 7: Commit**

```bash
git add tablerag/query/steps/expand.py tablerag/query/pipeline.py \
        tablerag/core/config.py tablerag/query/steps/assemble.py \
        tests/unit/test_expand_step.py
git commit -m "gather the context a chunk needs, behind a flag until it is measured"
```

---

### Task 6: Citation parsing moved to core, and the caution

**Files:**
- Create: `tablerag/core/citations.py`
- Modify: `tests/eval/qa/run_eval_qa.py` (import instead of redefine)
- Modify: `tablerag/core/schemas.py` (`Caution`, `Citation.expanded`)
- Test: `tests/unit/test_caution.py`

**Interfaces:**
- Consumes: `Citation` from `tablerag.core.schemas`
- Produces:
  - `cited_indices(answer: str) -> set[int]`
  - `caution_for(answer, citations, contact) -> Caution | None`
  - `Caution(BaseModel)`: `reasons: list[str]`, `contact: str | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_caution.py
import uuid

from tablerag.core.citations import caution_for, cited_indices
from tablerag.core.schemas import Citation


def _cite(index: int, **kw) -> Citation:
    base = dict(index=index, kind="text", doc_id=uuid.uuid4(),
                filename="notice.pdf", page=3, element_id=uuid.uuid4(),
                snippet="", score=0.5)
    base.update(kw)
    return Citation(**base)


def test_markers_are_read_out_of_the_answer():
    assert cited_indices("La garantie est de 100 % [1][3], voir [10].") \
        == {1, 3, 10}


def test_a_cited_figure_always_raises_a_caution():
    caution = caution_for("Le graphique montre 27 % [1].",
                          [_cite(1, from_figure=True)], contact=None)
    assert caution is not None
    assert any("figure" in reason or "image" in reason
               for reason in caution.reasons)


def test_a_cited_low_confidence_source_raises_one():
    caution = caution_for("La valeur est 34 900 [1].",
                          [_cite(1, confidence=0.4)], contact=None)
    assert caution is not None


def test_an_uncited_figure_does_not():
    caution = caution_for("La valeur est 34 900 [1].",
                          [_cite(1, confidence=1.0),
                           _cite(2, from_figure=True)], contact=None)
    assert caution is None


def test_the_contact_is_carried_through_when_the_kb_sets_one():
    caution = caution_for("Voir le graphique [1].",
                          [_cite(1, from_figure=True)],
                          contact="service RH du CETIAT")
    assert caution.contact == "service RH du CETIAT"


def test_with_no_markers_at_all_the_offered_sources_are_judged():
    caution = caution_for("La valeur n'est pas dans les documents.",
                          [_cite(1, from_figure=True)], contact=None)
    assert caution is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_caution.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tablerag.core.citations'`

- [ ] **Step 3: Write the module**

```python
# tablerag/core/citations.py
"""Reading citation markers back out of an answer, and what they oblige us to say.

The marker parser lives here rather than in the eval harness because two places
now need it — the gate that scores citations and the pipeline that decides
whether an answer needs a caution — and two copies of "what counts as a
citation" would eventually disagree about it.

The caution is a FIELD, not a sentence. A rule in the system prompt asking the
model to warn the user is omitted unpredictably by a 14B model, and editing that
prompt shifts the measured configuration for every query, including the ones
with no picture in them. As a field it fires whenever the condition holds and
the answer text does not change by one byte.
"""

from __future__ import annotations

import re

from tablerag.core.schemas import Caution, Citation

_MARKER = re.compile(r"\[(\d{1,3})\]")


def cited_indices(answer: str) -> set[int]:
    return {int(m) for m in _MARKER.findall(answer or "")}


def caution_for(answer: str, citations: list[Citation],
                contact: str | None,
                confidence_threshold: float = 0.9) -> Caution | None:
    """Whether this answer rests on something a human should check.

    Judged on what the model ACTUALLY cited; when it cited nothing, on
    everything it was offered — an answer with no markers is exactly the case
    where we know least about where it came from."""
    used = cited_indices(answer)
    relevant = [c for c in citations if not used or c.index in used]
    reasons: list[str] = []
    if any(c.from_figure for c in relevant):
        reasons.append("figure_reading")
    if any(c.needs_review for c in relevant):
        reasons.append("needs_review")
    if any(c.confidence is not None and c.confidence < confidence_threshold
           for c in relevant):
        reasons.append("low_confidence")
    if not reasons:
        return None
    return Caution(reasons=reasons, contact=contact)
```

- [ ] **Step 4: Add the schemas**

In `tablerag/core/schemas.py`, after `Citation`:

```python
class Caution(BaseModel):
    """Why this answer deserves a second look, and who to ask.

    `reasons` are stable machine keys, not prose: the UI renders them in the
    user's language, and an API consumer can act on them."""

    reasons: list[str] = []
    contact: str | None = None
```

and inside `Citation`, beside `from_figure`:

```python
    # pulled in because it neighbours a retrieved source, not because search
    # found it — a reader must be able to tell the two apart
    expanded: bool = False
```

- [ ] **Step 5: Make the eval harness use the shared parser**

In `tests/eval/qa/run_eval_qa.py`, replace the body of `cites()` with a call to
`cited_indices` from `tablerag.core.citations`, keeping its existing name and
signature so the rest of the harness is untouched.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/unit -q`
Expected: PASS (6 new tests)

- [ ] **Step 7: Commit**

```bash
git add tablerag/core/citations.py tablerag/core/schemas.py \
        tests/eval/qa/run_eval_qa.py tests/unit/test_caution.py
git commit -m "one definition of what counts as a citation, and what it obliges"
```

---

### Task 7: Caution through the API, contact from the KB

**Files:**
- Modify: `tablerag/api/routes/chat.py:50-80` (read config), stream tail
- Modify: `tablerag/query/pipeline.py` (`stream` yields the caution)
- Test: `tests/unit/test_chat_caution_stream.py`

**Interfaces:**
- Consumes: `caution_for` (Task 6)
- Produces: stream event `("caution", Caution | None)` after the last token;
  KB config key `escalation_contact`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_chat_caution_stream.py
import uuid

import pytest

from tablerag.core.schemas import Citation
from tablerag.query.pipeline import QueryContext


@pytest.mark.asyncio
async def test_the_stream_yields_a_caution_event_after_the_tokens():
    from tablerag.query.pipeline import caution_event

    ctx = QueryContext(kb_id=uuid.uuid4(), question="q")
    ctx.answer = "Le graphique montre 27 % [1]."
    ctx.citations = [Citation(index=1, kind="text", doc_id=uuid.uuid4(),
                              filename="f.pdf", page=1,
                              element_id=uuid.uuid4(), snippet="", score=0.1,
                              from_figure=True)]
    ctx.escalation_contact = "service RH"
    event = caution_event(ctx)
    assert event is not None
    assert event.contact == "service RH"
    assert "figure_reading" in event.reasons
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_chat_caution_stream.py -q`
Expected: FAIL — `ImportError: cannot import name 'caution_event'`

- [ ] **Step 3: Add the context field and the helper**

In `tablerag/query/pipeline.py`, add to `QueryContext`:

```python
    # per-KB: who to ask when an answer needs checking by a human. Lives in
    # KnowledgeBase.config, not a column — create_all adds tables, not columns.
    escalation_contact: str | None = None
```

and at module level:

```python
def caution_event(ctx: QueryContext):
    """The caution for a finished answer, or None. Never raises."""
    from tablerag.core.citations import caution_for

    try:
        return caution_for(ctx.answer, ctx.citations, ctx.escalation_contact)
    except Exception:  # noqa: BLE001 — a warning must not cost the answer
        logging.getLogger(__name__).exception("caution computation failed")
        return None
```

- [ ] **Step 4: Yield it from `stream`**

In `QueryPipeline.stream`, immediately before `yield "done", ctx`:

```python
        if (caution := caution_event(ctx)) is not None:
            yield "caution", caution
```

- [ ] **Step 5: Read the contact in the chat route and forward the event**

In `tablerag/api/routes/chat.py`, inside `prepare()` add
`contact = kb_config.get("escalation_contact")` to the returned tuple, set
`ctx.escalation_contact = contact`, and in `event_stream()` serialise the new
`"caution"` event the same way `"citations"` is serialised.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/unit -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tablerag/query/pipeline.py tablerag/api/routes/chat.py \
        tests/unit/test_chat_caution_stream.py
git commit -m "the warning is a field that always fires, not a sentence a model may forget"
```

---

### Task 8: Frontend — caution banner and the pulled-in label

**Files:**
- Modify: `frontend/lib/api.ts` (types + stream handling)
- Modify: `frontend/components/ChatPanel.tsx` (consume the event, render banner)
- Modify: `frontend/components/SourceModal.tsx` (the `ajouté par contexte` tag)
- Modify: `frontend/components/KbSettings.tsx:29-31` (add `escalation_contact`
  beside the existing `instructions` / `locale` / `verify` config fields)

**Interfaces:**
- Consumes: stream events `citations`, `caution`; `Citation.expanded`

- [ ] **Step 1: Add the types**

In `frontend/lib/api.ts`:

```ts
export type Caution = { reasons: string[]; contact: string | null };
```

and add `expanded: boolean` to the `Citation` type.

- [ ] **Step 2: Handle the new event**

Where the SSE stream is consumed, add a `caution` case storing it in state
alongside citations.

- [ ] **Step 3: Render the banner**

Below the answer, when a caution is present, render a bordered notice in the
same visual family as the existing `needs_review` badge. Map the reason keys to
French copy:

```ts
const CAUTION_COPY: Record<string, string> = {
  figure_reading: "Cette réponse s'appuie sur la lecture d'une image ou d'un graphique par le modèle, et non sur du texte imprimé.",
  low_confidence: "Une des sources citées a été analysée avec une confiance faible.",
  needs_review: "Une des sources citées est signalée comme à vérifier.",
};
```

with a closing line: `Vérifiez le document d'origine` plus
`, ou contactez ${caution.contact}` when a contact is set.

- [ ] **Step 4: Label expanded citations**

In the citation list, when `citation.expanded` is true, add a muted tag reading
`ajouté par contexte`.

- [ ] **Step 5: Add the KB setting**

In the KB settings form, add a text input bound to `config.escalation_contact`,
labelled `Contact en cas de doute` with helper text
`ex. service RH du CETIAT — affiché quand une réponse demande vérification`.

- [ ] **Step 6: Build**

Run: `cd frontend && npx next build`
Expected: build succeeds with no type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "show the reader which sources were found and which were brought along"
```

---

### Task 9: Measure it, or drop it

**Files:**
- Modify: `tests/eval/qa/questions.jsonl`
- Create: `docs/superpowers/plans/2026-08-11-answer-completeness-results.md`

**This task cannot start until the user names a real sibling-table pair in the
corpus** (same document or different; distinguished by year or by department).
Everything above is implementable without it; nothing above may be declared
worth keeping without it.

- [ ] **Step 1: Write the trap questions**

Add to `tests/eval/qa/questions.jsonl`, using the real pair once identified: at
least three questions whose correct answer requires distinguishing the siblings
(one naming the period explicitly, one naming neither — where the correct
behaviour is to give BOTH attributed), and two for a real A->B->C split where
the answer needs the paragraph before or after the keyword-bearing one.

- [ ] **Step 2: Watch them fail**

Run: `make eval-qa KB=<kb_id>`
Expected: the new questions FAIL. If they pass with the flag off, they are not
testing what they were written to test — rewrite them before going further.

- [ ] **Step 3: Record the baseline**

Write the failing numbers into the results file, with the date and the KB.

- [ ] **Step 4: Confirm the budget does not bind**

Run: `make eval-qa KB=<kb_id>` and grep the API logs for
`context budget exceeded`. Expected: no hits with `chat_num_ctx=32768`. If there
are hits, that is pre-existing silent truncation now made visible — record it,
it is news.

- [ ] **Step 5: Turn expansion on and measure again**

Set `LEDGERRAG_EXPAND_NEIGHBOURS=true`, restart the API, re-run
`make eval-qa KB=<kb_id>`.

- [ ] **Step 6: Decide from the numbers**

If the trap questions now pass and nothing else regressed, change the default to
`True` in `config.py` and record it. **If the numbers do not move, revert the
default and record that too** — a feature that sounds right and measures flat is
a feature this project does not keep.

- [ ] **Step 7: Commit**

```bash
git add tests/eval/qa/questions.jsonl docs/superpowers/plans/*results.md
git commit -m "what the gate said about expansion and contrast"
```
