"""Retrieve step. Phase 2: dense search over all three collections
(chunks / records / table_summaries), merged by score — same embedder and
cosine metric, so scores are comparable.

Phase 4 upgrades this slot to hybrid dense+sparse with RRF fusion.
"""

from __future__ import annotations

from tablerag.models.registry import get_provider
from tablerag.query.pipeline import QueryContext
from tablerag.storage.qdrant import (
    ALL_COLLECTIONS,
    get_vector_store,
)


class Retrieve:
    def __init__(self, top_k: int = 12):
        self.top_k = top_k

    async def run(self, ctx: QueryContext) -> QueryContext:
        embedder = get_provider("embedder")
        [query_vector] = await embedder.embed([ctx.question])
        store = get_vector_store()
        hits = []
        for collection in ALL_COLLECTIONS:
            for hit in store.search(collection, query_vector.dense,
                                    ctx.routed_kb_ids, self.top_k):
                hit.payload["_collection"] = collection
                hits.append(hit)
        hits.sort(key=lambda h: h.score, reverse=True)
        ctx.hits = hits[:self.top_k]
        return ctx
