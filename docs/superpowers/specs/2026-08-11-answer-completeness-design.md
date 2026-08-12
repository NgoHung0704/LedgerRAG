# Answer completeness: neighbour expansion, overlap contrast, calibrated caution

Design agreed 2026-08-11. Three changes to the query pipeline, one shared
constraint. None of them is adopted until `make eval-qa` moves.

## The problem

Three failures reported from use, all about an answer that is *incomplete* or
*falsely confident* rather than wrong:

1. **Split meaning.** Chunk A leads into B, C continues it. B carries the
   keyword, so B is retrieved and A and C are not — the answer quotes B without
   what makes B mean anything.
2. **Look-alike duplicates.** Chunk D matches B's keywords and topic but covers a
   different period or department. Both are retrieved, the answer merges them,
   and nobody can tell it merged.
3. **Confident reading of a picture.** A figure description, a chart value or a
   colour code is a model's *reading of an image*, not text printed on the page.
   Today it is presented with the same voice as a quoted number.

## The constraint everything lives under

`tablerag/core/config.py` records the hazard already:

> the assembled sources easily exceed Ollama's default num_ctx, **which then
> drops the TOP of the prompt**

The top of the prompt is `SYSTEM_PROMPT` — the honesty rules, the copy-numbers
-exactly rule, the LOW CONFIDENCE rule. **Overflowing the window silently
removes every safety rule at once, in exactly the situations where the context
got big because the question was hard.** Raising `chat_num_ctx` to 32768 raises
the cliff; it does not remove it.

There is no total budget today, only a per-table cap (`TABLE_HTML_LIMIT`).
Twelve sources with two large tables already exceed 16384 tokens; it has not
bitten yet only because large tables rarely win together. Neighbour expansion
turns that gap into a routine event, so the budget comes first.

## 1. Assembly budget

`AssembleContext` gains a deterministic total cap derived from config, not
hardcoded:

```
budget_chars = (chat_num_ctx - reserve_tokens) * CHARS_PER_TOKEN
```

`CHARS_PER_TOKEN = 3.0` deliberately **under**estimates French (~3.5-4 in
practice) so the error falls on the safe side. `reserve_tokens = 3000` covers
the system prompt (~1200 tokens with both conditional rules) plus room for the
answer. Both live beside `TABLE_HTML_LIMIT` in `assemble.py`.

**The budget applies whether or not expansion is enabled, so it is itself a
behaviour change and is measured like one.** With `chat_num_ctx = 32768` it
should never bind on the current eval set — that must be *verified* by running
`make eval-qa` with trim logging on and confirming nothing was trimmed, not
assumed. If it does bind today, that is a pre-existing silent truncation the
budget has just made visible, and it is news worth having.

When the budget is exceeded, the sacrifice order is fixed and logged:

1. expanded neighbours, lowest rank first
2. then lowest-ranked primary sources
3. tables are truncated last
4. **the top-ranked source is never dropped**

Trimming logs at warning level naming what was dropped. This is the point: today
Ollama chooses, blind, from the top, and nobody knows. After this we choose,
from the least valuable end, and it is visible.

`TABLE_HTML_LIMIT` moves 12000 -> 24000, tracking the `chat_num_ctx` change to
32768 the operator is making.

## 2. Neighbour expansion

New step `ExpandNeighbours`, **after Rerank, before AssembleContext** — after
rerank so it cannot dilute ranking, before assemble so it is subject to the
budget.

- For each winning **text** source: the elements immediately before and after it
  in reading order within the same document (page, then bbox y).
- For each winning source of any kind: **every table and figure on that page**.
- Tables and figures do **not** pull their own neighbours. Otherwise one table
  pulls its page, which pulls more, and it cascades.
- Nothing already present is added twice.

Each expanded item becomes its **own numbered source**, ordered after all
primary sources, labelled "pulled in as context". The flag `expanded: bool` is
added to **both** `SourceBlock` and `Citation` — `Citation` is the client
contract, and a UI that cannot tell retrieved from pulled-in cannot show it.
Traceability stays honest — a fact from page 6 cites page 6, not page 5 — and a
reader can still see what retrieval actually found.

This **moves citation counts**, so it ships behind `expand_neighbours = False`
and is measured A/B before any default changes.

## 3. Overlap contrast

New pure module `tablerag/query/overlap.py`, no DB access, testable on
fabricated blocks:

- `header_signature(html)` — normalise header cells (strip accents, digits,
  case), sort, hash. Equal signature = structural siblings. This is exactly the
  reported case: same structure, different numbers.
- `subject_signature(text)` — content words after stopword removal, keeping the
  **rare** terms. Jaccard over all words false-positives everywhere, because
  French boilerplate repeats across every document in the corpus.
- `group_overlapping(blocks) -> list[list[int]]`

**What is computed is provenance difference, not semantic difference.** The
machine can state which document, which page, which heading above it
(`meta["context"]`), and a period token — a 4-digit year or a `T1`/`Q1`-shaped
quarter matched by regex in the heading or filename, nothing cleverer. It cannot
compute what the two sources *say* differently. So the note injected into
context says only what it knows:

```
[2] and [5] are the same kind of table, from different sources:
  [2] Notice 2024 - « Garanties optique »
  [5] Notice 2025 - « Garanties optique »
```

`OVERLAP_RULE` — conditional, in the shape of the existing `FIGURE_RULE`,
appended only when a group exists — requires the model to: never flatten the
group into one statement; attribute each version to its document; say plainly
when they disagree; **and when the question does not name a document or period,
give both attributed rather than choosing for the user.**

Because the rule is conditional, a query with no overlap keeps the answering
prompt byte-identical to the measured configuration.

**The Jaccard threshold is not guessed here.** It is measured on the corpus, the
same way the two thresholds recorded as rejected in `drawn_around_text` were.

## 4. Calibrated caution

Rejected approach: a new rule in `SYSTEM_PROMPT` telling the model to write a
caution sentence. A 14B model omits it unpredictably, and every `SYSTEM_PROMPT`
edit shifts the measured configuration for **all** queries, including those with
no picture in sight.

Instead the caution is a **structured response field, not prose in the answer**:

```python
caution: {reason: list[str], contact: str | None} | None
```

Computed deterministically at `done`, from the sources the model **actually
cited**, falling back to the sources offered when it cites nothing. Marker
parsing is new code in `tablerag/core/citations.py` — an earlier draft of this
spec said it already existed in the eval harness and only needed moving, which
was wrong: `cites()` there matches a citation against a document name and never
reads `[n]` markers at all. It fires when a cited source is
`from_figure=True`, or `needs_review`, or `confidence <
confidence_review_threshold` (0.9, already in config). A distinct reason is
added when the figure's palette satisfies `is_colour_coded()` — reusing
`tablerag/ingestion/palette.py` — because a colour code is the hardest thing to
read off a page and has no printed words to check it against.

`contact` comes from a new optional per-KB field. Unset, the caution names "the
department that issued the document" generically.

The frontend renders it as a banner, in the same family as the existing
`needs_review` badges.

Decisive property: **the answer text does not change by one byte**, so
`eval-qa` cannot drift because of this feature, and the caution appears whenever
the condition holds instead of whenever the model remembers.

## Failure handling

None of the three may fail an answer — the rule already applied to figures
("a figure must never fail a document"). Expansion fails -> primary sources
only. Overlap detection fails -> no note. Caution computation fails -> no
banner. Each logs. The answer still goes out.

## Tests

Unit, pure, no DB and no model:

- `header_signature` groups two sibling tables and separates two differently
  shaped ones
- `subject_signature` does not group two chunks that merely share boilerplate
- neighbour selection picks the elements immediately before/after in reading
  order, and a **table pulls no neighbours**
- budget trimming sacrifices expansions first and **never drops rank 1**
- caution fires on a cited figure / `needs_review` / low-confidence source, and
  stays silent otherwise

## Measurement, and what blocks it

Order, per the project's rule that a gate is written before the fix:

1. Write trap questions for a real sibling-table pair, and for a real A->B->C
   split, into `tests/eval/qa/questions.jsonl`
2. Run `make eval-qa` and **watch them fail**
3. Enable `expand_neighbours`, measure again

If the numbers do not move, the feature is not kept, however reasonable it
sounds.

**Blocked:** the trap questions cannot be written yet — no specific sibling-table
pair has been identified in the corpus (same document or different, distinguished
by year or by department). This blocks step 1, not the implementation.

## Out of scope

Putting scope words into record text (discussed, separate change, needs its own
measurement); page-neighbourhood ranking boost; reranker activation.
