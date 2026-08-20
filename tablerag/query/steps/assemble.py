"""AssembleContext step: hydrate hits from Postgres into SourceBlocks.

- chunk hits -> their text, with provenance.
- record / table_summary hits -> the WHOLE parent table (HTML + summary),
  never a lone record (SPEC Phase 2 §6), deduped per table element.

Every block carries crop path, confidence and needs_review so Generate and
the frontend can honor the honest-failure contract (principle #3, §0.3).
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
import uuid

from tablerag.core.schemas import Citation
from tablerag.core.table_text import flatten_table_for_context, html_to_text
from tablerag.query.pipeline import QueryContext, SourceBlock
from tablerag.query.steps.rerank import relevance_of
from tablerag.storage.db import session_scope
from tablerag.storage.qdrant import COLLECTION_CHUNKS
from tablerag.storage.repositories import (
    ChunkContext,
    TableSource,
    get_chunk_contexts,
    get_element_chunk_contexts,
    get_record_dimensions,
    get_record_texts,
    get_table_sources,
)

logger = logging.getLogger(__name__)

_WORD_CHARS = re.compile(r"[^0-9a-z]+")


def _fold(text: str) -> str:
    """Lowercase, strip accents, keep letters and DIGITS.

    Unlike overlap._fold, which drops everything that is not a letter: the
    values matched here are mostly numbers, so folding them away would leave
    nothing to match on."""
    stripped = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def _spoken(needle: str, haystack: str) -> bool:
    """Is `needle` said in `haystack`, on whole-word boundaries?

    Boundaries are the point: without them "la classe 10" matches a row whose
    class is 100, and the answer names employments from a class nobody asked
    about."""
    needle = _WORD_CHARS.sub(" ", _fold(needle)).strip()
    if not needle:
        return False
    return re.search(rf"(?<![0-9a-z]){re.escape(needle)}(?![0-9a-z])",
                     _WORD_CHARS.sub(" ", _fold(haystack))) is not None


def rows_by_named_value(question: str, records) -> list:
    """Ids of the rows the question names by value — read, not ranked.

    A question like "les emplois de la classe d'emploi 10" is a FILTER: it
    wants every row whose `classe` is 10. Dense retrieval cannot serve it —
    `classe: 10` and `classe: 11` embed almost identically, and every row of a
    table shares its filename, heading and column names — so no record ranks,
    the table arrives through its summary alone, and the assistant reads the
    flattened grid and guesses. Measured on the box: rows=0 answered with two
    employments from the wrong class; rows=1, twenty-five seconds later,
    answered correctly.

    The table is already retrieved when this runs, so its own rows can simply
    be read. No model, no threshold, no drift.

    BOTH halves must be present — the column's NAME and its VALUE. A table of
    gradings is full of bare numbers, so matching on the value alone would pull
    in every row with a cotation of 10, which is the look-alike failure this
    exists to end. Only `dimensions` are searched: metrics are the figures an
    answer quotes, and matching on them would select a row because the question
    mentioned a salary rather than because it named that row.

    `records` is (id, dimensions) pairs, so this stays a pure function the
    tests can drive without a database.
    """
    if not question:
        return []
    out = []
    for record_id, dimensions in records:
        for column, value in (dimensions or {}).items():
            if _spoken(column, question) and _spoken(value, question):
                out.append(record_id)
                break
    return out


SNIPPET_CHARS = 240
# must hold a full multi-page merged table: truncating mid-table silently
# amputates the later rows (the Glossaire cross-page table is ~2x the old
# 6000 limit). Budgeted against chat_num_ctx=32768.
TABLE_HTML_LIMIT = 24000
# how many matched rows to surface above a table before it becomes noise again
MAX_MATCHED_ROWS = 4
# Rows selected by rows_by_named_value get their own, larger budget. Those four
# are a similarity guess and more of them are more noise; these are the exact
# answer to a filter ("which employments are in class 10"), and cutting the
# list at four turns a complete answer into a silently partial one — the reader
# sees a confident list and cannot tell rows were dropped.
MAX_NAMED_ROWS = 12
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


class AssembleContext:
    async def run(self, ctx: QueryContext) -> QueryContext:
        chunk_ids: list[uuid.UUID] = []
        chunk_scores: dict[uuid.UUID, float] = {}
        table_ids: list[uuid.UUID] = []
        table_scores: dict[uuid.UUID, float] = {}
        # which rows made this table match, in relevance order (see MAX_MATCHED_ROWS)
        matched: dict[uuid.UUID, list[uuid.UUID]] = {}

        # rank = position in ctx.hits, which is the order the Rerank step
        # decided (reranker scores, or document-diversified fallback). It is
        # NOT the raw fusion score: re-sorting by score here silently threw
        # that decision away and made both reranking and diversification no-ops.
        rank: dict[tuple[str, uuid.UUID], int] = {}

        # elements pulled in by ExpandNeighbours. They arrive as ELEMENT ids,
        # and the loop below would otherwise send every one of them down the
        # table path — where a text or figure neighbour has no parent table and
        # would disappear with no error at all.
        expanded_ids: set[uuid.UUID] = set()
        expanded_elements: list[uuid.UUID] = []
        expanded_rank: dict[uuid.UUID, int] = {}

        for position, hit in enumerate(ctx.hits):
            if hit.payload.get("_expanded"):
                raw = hit.payload.get("element_id")
                if raw is None:
                    continue
                element_id = uuid.UUID(raw)
                expanded_ids.add(element_id)
                if hit.payload.get("element_type") == "table":
                    if element_id not in table_scores:
                        table_ids.append(element_id)
                        table_scores[element_id] = hit.score
                        rank[("table", element_id)] = position
                elif element_id not in expanded_rank:
                    expanded_elements.append(element_id)
                    expanded_rank[element_id] = position
                continue
            if hit.payload.get("_collection") == COLLECTION_CHUNKS:
                raw = hit.payload.get("chunk_id")
                if raw is None:
                    continue
                chunk_id = uuid.UUID(raw)
                if chunk_id not in chunk_scores:
                    chunk_ids.append(chunk_id)
                    # what the reranker judged, not what retrieval fused: the
                    # number a reader is shown must mean "this answered the
                    # question", not "several searches agreed to look here"
                    chunk_scores[chunk_id] = relevance_of(hit)
                    rank[("text", chunk_id)] = position
            else:  # records / table_summaries -> parent table element
                raw = hit.payload.get("element_id")
                if raw is None:
                    continue
                element_id = uuid.UUID(raw)
                if element_id not in table_scores:
                    table_ids.append(element_id)
                    table_scores[element_id] = relevance_of(hit)
                    rank[("table", element_id)] = position
                record_raw = hit.payload.get("record_id")
                if record_raw:
                    rows = matched.setdefault(element_id, [])
                    record_id = uuid.UUID(record_raw)
                    if record_id not in rows:
                        rows.append(record_id)

        chunks, tables, record_texts, expanded_chunks, named =             await asyncio.to_thread(self._fetch, chunk_ids, table_ids, matched,
                                    expanded_elements, ctx.question)

        # an expanded chunk scores 0.0: it was never retrieved, and giving it a
        # borrowed score would let it compete with what search actually found
        for extra in expanded_chunks:
            if extra.chunk_id in chunk_scores:
                continue
            chunks.append(extra)
            chunk_scores[extra.chunk_id] = 0.0
            rank[("text", extra.chunk_id)] = expanded_rank.get(
                extra.element_id, len(ctx.hits))

        blocks: list[SourceBlock] = [self._text_block(c, chunk_scores) for c in chunks]
        blocks += [self._table_block(t, table_scores,
                                     *self._rows_for(t.element_id, matched,
                                                     named, record_texts))
                   for t in tables]
        # Does representation 2 take part at all? A table block is summary +
        # the rows that matched + THE WHOLE GRID, and the grid is always there.
        # Two very different problems hide behind the same wrong answer: rows
        # matched and the model read the grid anyway (cheap to fix - stop
        # sending the grid), or rows never matched at all (records are not
        # reaching retrieval, and that is a change to how they are built).
        # Nothing distinguished them, so the choice was a guess.
        if tables:
            logger.info("tables: %s", " | ".join(
                f"{t.filename[:26]} p{t.page} rows={len(matched.get(t.element_id, []))}"
                f" named={len(named.get(t.element_id, []))}"
                f" grid={len(t.html or '')}" for t in tables))

        for block in blocks:
            block.expanded = block.element_id in expanded_ids
        blocks.sort(key=lambda b: rank.get(
            (b.kind, b.chunk_id if b.kind == "text" else b.element_id),
            len(ctx.hits)))

        from tablerag.core.config import get_settings

        blocks, sacrificed = trim_to_budget(blocks, budget_chars(get_settings()))
        if sacrificed:
            # the one moment a user is at risk of an incomplete answer through
            # no fault of retrieval — it must be visible in the logs
            logger.warning("context budget exceeded, sacrificed: %s",
                           "; ".join(sacrificed))
        ctx.sources = blocks
        ctx.citations = [
            Citation(index=i + 1, kind=b.kind, doc_id=b.doc_id,
                     filename=b.filename, page=b.page, element_id=b.element_id,
                     chunk_id=b.chunk_id, snippet=b.snippet, score=b.score,
                     crop_image_path=b.crop_image_path,
                     confidence=b.confidence, needs_review=b.needs_review,
                     expanded=b.expanded,
                     from_figure=b.from_figure)
            for i, b in enumerate(blocks)
        ]
        return ctx

    @staticmethod
    def _text_block(c: ChunkContext, scores: dict) -> SourceBlock:
        return SourceBlock(
            kind="text", doc_id=c.doc_id, filename=c.filename, page=c.page,
            element_id=c.element_id, chunk_id=c.chunk_id, content=c.text,
            snippet=c.text[:SNIPPET_CHARS], score=scores.get(c.chunk_id, 0.0),
            crop_image_path=c.crop_image_path, confidence=c.confidence,
            needs_review=c.needs_review,
            from_figure=c.element_type == "figure", context=c.context)

    @staticmethod
    def _table_block(t: TableSource, scores: dict,
                     matched_rows: list[str] | None = None,
                     ranked: bool = True) -> SourceBlock:
        parts = []
        if t.summary:
            parts.append(f"Table summary: {t.summary}")
        # Rows ahead of the full grid: a small model asked for one cell
        # otherwise has to scan a 19-row table among a dozen sources (run 2:
        # values read off the wrong row/table).
        #
        # The HEADING depends on how they were chosen, and that is not a
        # nicety. Read rows went in under the ranked rows' wording, "Rows
        # matching the question", which for a string match is simply false. p6
        # asks for the AVERAGE salary of the classes in group F; the matcher
        # surfaced every group-F row, the heading said they matched the
        # question, and the model stated per-class MINIMA as an average. A trap
        # that had passed since Phase 4 started failing. The rows were worth
        # having; the claim about them was not.
        if matched_rows:
            parts.append(
                ("Rows matching the question:\n" if ranked else
                 "Rows of this table that repeat wording from the question. "
                 "They were selected by matching text, NOT because they answer "
                 "what was asked — check the column asked for before quoting "
                 "one:\n")
                + "\n".join(f"- {row}" for row in matched_rows))
        if t.html:
            # merged cells expanded: rowspan/colspan are for DISPLAY, and
            # reading them back positionally is exactly how a small model
            # lands a value in the wrong column (see flatten_table_for_context)
            parts.append(flatten_table_for_context(t.html)[:TABLE_HTML_LIMIT])
        content = "\n".join(parts) or "(table could not be parsed — image only)"
        # citation snippets are shown to end users: never raw markup
        snippet = (t.summary or html_to_text(t.html) or "table")[:SNIPPET_CHARS]
        return SourceBlock(
            kind="table", doc_id=t.doc_id, filename=t.filename, page=t.page,
            element_id=t.element_id, content=content, snippet=snippet,
            score=scores.get(t.element_id, 0.0),
            crop_image_path=t.crop_image_path, confidence=t.confidence,
            needs_review=t.needs_review, context=t.context)

    @staticmethod
    def _named_rows(s, unranked: list[uuid.UUID],
                    question: str) -> dict[uuid.UUID, list[uuid.UUID]]:
        """Rows read off the tables that reached context without ranking any.

        Auxiliary by construction: without it the full grid is still in the
        prompt and the model still answers, just less reliably. So a failure
        here costs the ROWS, never the reply — the same contract
        group_overlapping states two steps away in this pipeline, and the one
        this shipped without.
        """
        if not unranked or not question:
            return {}
        named: dict[uuid.UUID, list[uuid.UUID]] = {}
        try:
            for element_id, rows in get_record_dimensions(s, unranked).items():
                hits = rows_by_named_value(question, rows)[:MAX_NAMED_ROWS]
                if hits:
                    named[element_id] = hits
        except Exception:  # noqa: BLE001 — see the docstring: never fatal
            logger.exception("named-row lookup failed (non-fatal)")
            return {}
        return named

    @staticmethod
    def _rows_for(element_id, matched: dict, named: dict,
                  record_texts: dict) -> tuple[list[str], bool]:
        """The rows shown above this table's grid, and whether they were RANKED.

        Ranked rows first, capped tight because more of a similarity guess is
        more noise. Only when there were NONE do the read rows stand in, on
        their own larger budget: they are the exact answer to a filter, and
        trimming them to four would turn a complete list into a silently
        partial one.

        The flag travels with the rows because the prompt has to say which kind
        it got. Ranked rows earned "matching the question"; read rows matched a
        string, and telling the model otherwise is what made it quote per-class
        minima as an average."""
        ranked = [record_texts[r] for r in matched.get(element_id, [])
                  if r in record_texts][:MAX_MATCHED_ROWS]
        if ranked:
            return ranked, True
        return [record_texts[r] for r in named.get(element_id, [])
                if r in record_texts][:MAX_NAMED_ROWS], False

    @staticmethod
    def _fetch(chunk_ids: list[uuid.UUID], table_ids: list[uuid.UUID],
               matched: dict[uuid.UUID, list[uuid.UUID]],
               expanded_elements: list[uuid.UUID] | None = None,
               question: str = "") -> tuple[list, list, dict, list, dict]:
        record_ids = [r for rows in matched.values()
                      for r in rows[:MAX_MATCHED_ROWS]]
        # Tables that reached the context WITHOUT a row of their own. A filter
        # question cannot rank rows — every row of a table shares its filename,
        # heading and column names — so the table arrives through its summary
        # and the assistant reads the grid and guesses. These rows are read
        # instead of ranked.
        unranked = [t for t in table_ids if not matched.get(t)]
        with session_scope() as s:
            named = AssembleContext._named_rows(s, unranked, question)
            record_ids += [r for rows in named.values() for r in rows]
            return (get_chunk_contexts(s, chunk_ids),
                    get_table_sources(s, table_ids),
                    get_record_texts(s, record_ids),
                    get_element_chunk_contexts(s, expanded_elements or []),
                    named)
