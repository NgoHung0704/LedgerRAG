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
    get_table_sources,
)

SNIPPET_CHARS = 240
TABLE_HTML_LIMIT = 6000


class AssembleContext:
    async def run(self, ctx: QueryContext) -> QueryContext:
        chunk_ids: list[uuid.UUID] = []
        chunk_scores: dict[uuid.UUID, float] = {}
        table_ids: list[uuid.UUID] = []
        table_scores: dict[uuid.UUID, float] = {}

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

        chunks, tables = await asyncio.to_thread(self._fetch, chunk_ids, table_ids)

        blocks: list[SourceBlock] = [self._text_block(c, chunk_scores) for c in chunks]
        blocks += [self._table_block(t, table_scores) for t in tables]
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
    def _table_block(t: TableSource, scores: dict) -> SourceBlock:
        parts = []
        if t.summary:
            parts.append(f"Table summary: {t.summary}")
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
    def _fetch(chunk_ids: list[uuid.UUID],
               table_ids: list[uuid.UUID]) -> tuple[list, list]:
        with session_scope() as s:
            return (get_chunk_contexts(s, chunk_ids),
                    get_table_sources(s, table_ids))
