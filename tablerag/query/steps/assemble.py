"""AssembleContext step: hydrate hits from Postgres into SourceBlocks.

- chunk hits -> their text, with provenance.
- record / table_summary hits -> the WHOLE parent table (HTML + summary),
  never a lone record (SPEC Phase 2 §6), deduped per table element.

Every block carries crop path, confidence and needs_review so Generate and
the frontend can honor the honest-failure contract (principle #3, §0.3).
"""

from __future__ import annotations

import asyncio
import uuid

from tablerag.core.schemas import Citation
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

SNIPPET_CHARS = 240
# must hold a full multi-page merged table: truncating mid-table silently
# amputates the later rows (the Glossaire cross-page table is ~2x the old
# 6000 limit). Budgeted against chat_num_ctx=16384.
TABLE_HTML_LIMIT = 12000
# how many matched rows to surface above a table before it becomes noise again
MAX_MATCHED_ROWS = 4


class AssembleContext:
    async def run(self, ctx: QueryContext) -> QueryContext:
        chunk_ids: list[uuid.UUID] = []
        chunk_scores: dict[uuid.UUID, float] = {}
        table_ids: list[uuid.UUID] = []
        table_scores: dict[uuid.UUID, float] = {}
        # which rows made this table match, in relevance order (see MAX_MATCHED_ROWS)
        matched: dict[uuid.UUID, list[uuid.UUID]] = {}

        for hit in ctx.hits:  # already sorted by score desc
            if hit.payload.get("_collection") == COLLECTION_CHUNKS:
                raw = hit.payload.get("chunk_id")
                if raw is None:
                    continue
                chunk_id = uuid.UUID(raw)
                if chunk_id not in chunk_scores:
                    chunk_ids.append(chunk_id)
                    chunk_scores[chunk_id] = hit.score
            else:  # records / table_summaries -> parent table element
                raw = hit.payload.get("element_id")
                if raw is None:
                    continue
                element_id = uuid.UUID(raw)
                if element_id not in table_scores:
                    table_ids.append(element_id)
                    table_scores[element_id] = hit.score
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
        blocks.sort(key=lambda b: b.score, reverse=True)

        ctx.sources = blocks
        ctx.citations = [
            Citation(index=i + 1, kind=b.kind, doc_id=b.doc_id,
                     filename=b.filename, page=b.page, element_id=b.element_id,
                     chunk_id=b.chunk_id, snippet=b.snippet, score=b.score,
                     crop_image_path=b.crop_image_path,
                     confidence=b.confidence, needs_review=b.needs_review)
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
            needs_review=c.needs_review)

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
            parts.append(t.html[:TABLE_HTML_LIMIT])
        content = "\n".join(parts) or "(table could not be parsed — image only)"
        snippet = (t.summary or t.html or "table")[:SNIPPET_CHARS]
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
