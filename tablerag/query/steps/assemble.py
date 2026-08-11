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
import uuid

from tablerag.core.schemas import Citation
from tablerag.core.table_text import flatten_table_for_context, html_to_text
from tablerag.query.pipeline import QueryContext, SourceBlock
from tablerag.storage.db import session_scope
from tablerag.storage.qdrant import COLLECTION_CHUNKS
from tablerag.storage.repositories import (
    ChunkContext,
    TableSource,
    get_chunk_contexts,
    get_record_texts,
    get_table_sources,
)

logger = logging.getLogger(__name__)

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

    Blocks arrive in rank order with expanded neighbours last, so dropping from
    the END gives exactly the order the design calls for: expansions first
    (lowest rank first), then the lowest-ranked primary sources. The top-ranked
    source is never dropped — if it alone exceeds the budget it is truncated,
    because returning nothing is worse than returning a shortened best source.

    Returns the kept blocks and a description of every sacrifice, so the caller
    can log what the user did not get to see.
    """
    dropped: list[str] = []
    kept = list(blocks)

    def total() -> int:
        return sum(len(b.content) for b in kept)

    while len(kept) > 1 and total() > budget:
        gone = kept.pop()
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

        for position, hit in enumerate(ctx.hits):
            if hit.payload.get("_collection") == COLLECTION_CHUNKS:
                raw = hit.payload.get("chunk_id")
                if raw is None:
                    continue
                chunk_id = uuid.UUID(raw)
                if chunk_id not in chunk_scores:
                    chunk_ids.append(chunk_id)
                    chunk_scores[chunk_id] = hit.score
                    rank[("text", chunk_id)] = position
            else:  # records / table_summaries -> parent table element
                raw = hit.payload.get("element_id")
                if raw is None:
                    continue
                element_id = uuid.UUID(raw)
                if element_id not in table_scores:
                    table_ids.append(element_id)
                    table_scores[element_id] = hit.score
                    rank[("table", element_id)] = position
                record_raw = hit.payload.get("record_id")
                if record_raw:
                    rows = matched.setdefault(element_id, [])
                    record_id = uuid.UUID(record_raw)
                    if record_id not in rows:
                        rows.append(record_id)

        chunks, tables, record_texts = await asyncio.to_thread(
            self._fetch, chunk_ids, table_ids, matched)

        blocks: list[SourceBlock] = [self._text_block(c, chunk_scores) for c in chunks]
        blocks += [self._table_block(t, table_scores,
                                     [record_texts[r] for r in matched.get(t.element_id, [])
                                      if r in record_texts][:MAX_MATCHED_ROWS])
                   for t in tables]
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
            from_figure=c.element_type == "figure")

    @staticmethod
    def _table_block(t: TableSource, scores: dict,
                     matched_rows: list[str] | None = None) -> SourceBlock:
        parts = []
        if t.summary:
            parts.append(f"Table summary: {t.summary}")
        # the rows that actually matched the question, ahead of the full grid:
        # a small model asked for one cell otherwise has to scan a 19-row table
        # among a dozen sources (run 2: values read off the wrong row/table)
        if matched_rows:
            parts.append("Rows matching the question:\n"
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
            needs_review=t.needs_review)

    @staticmethod
    def _fetch(chunk_ids: list[uuid.UUID], table_ids: list[uuid.UUID],
               matched: dict[uuid.UUID, list[uuid.UUID]]
               ) -> tuple[list, list, dict]:
        record_ids = [r for rows in matched.values()
                      for r in rows[:MAX_MATCHED_ROWS]]
        with session_scope() as s:
            return (get_chunk_contexts(s, chunk_ids),
                    get_table_sources(s, table_ids),
                    get_record_texts(s, record_ids))
