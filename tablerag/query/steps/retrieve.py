"""Retrieve step. Phase 1: dense-only over the `chunks` collection.

Phase 4 upgrades this to hybrid dense+sparse with RRF fusion across all three
collections (chunks / records / table_summaries) — same step slot.
"""

from __future__ import annotations

from tablerag.models.registry import get_provider
from tablerag.query.pipeline import QueryContext
from tablerag.storage.qdrant import COLLECTION_CHUNKS, get_vector_store


class Retrieve:
    def __init__(self, top_k: int = 12):
        self.top_k = top_k

    async def run(self, ctx: QueryContext) -> QueryContext:
        embedder = get_provider("embedder")
        [query_vector] = await embedder.embed([ctx.question])
        ctx.hits = get_vector_store().search(
            COLLECTION_CHUNKS, query_vector.dense, ctx.routed_kb_ids, self.top_k)
        return ctx
