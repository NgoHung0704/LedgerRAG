"""AssembleContext step: hydrate hits from Postgres and build citations.

Every citation carries full provenance (principle #3): doc, page, element,
crop image path, confidence, needs_review. From Phase 2 on, record hits pull
in their parent table's HTML here; Phase 3 makes low-confidence sources warn.
"""

from __future__ import annotations

import asyncio
import uuid

from tablerag.core.schemas import Citation
from tablerag.query.pipeline import QueryContext
from tablerag.storage.db import session_scope
from tablerag.storage.repositories import ChunkContext, get_chunk_contexts

SNIPPET_CHARS = 240


class AssembleContext:
    async def run(self, ctx: QueryContext) -> QueryContext:
        chunk_ids: list[uuid.UUID] = []
        scores: dict[uuid.UUID, float] = {}
        for hit in ctx.hits:
            raw = hit.payload.get("chunk_id")
            if raw is None:
                continue
            chunk_id = uuid.UUID(raw)
            if chunk_id not in scores:  # dedupe, keep best (first = highest) score
                chunk_ids.append(chunk_id)
                scores[chunk_id] = hit.score

        contexts = await asyncio.to_thread(self._fetch, chunk_ids)
        ctx.contexts = contexts
        ctx.citations = [
            Citation(
                index=i + 1,
                doc_id=c.doc_id, filename=c.filename, page=c.page,
                element_id=c.element_id, chunk_id=c.chunk_id,
                snippet=c.text[:SNIPPET_CHARS],
                score=scores.get(c.chunk_id, 0.0),
                crop_image_path=c.crop_image_path,
                confidence=c.confidence, needs_review=c.needs_review)
            for i, c in enumerate(contexts)
        ]
        return ctx

    @staticmethod
    def _fetch(chunk_ids: list[uuid.UUID]) -> list[ChunkContext]:
        with session_scope() as s:
            return get_chunk_contexts(s, chunk_ids)
