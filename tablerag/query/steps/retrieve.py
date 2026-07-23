"""Retrieve step (Phase 4): hybrid dense+sparse with RRF fusion over all
three collections (chunks / records / table_summaries), merged by score.

Sparse lexical matching catches the rare tokens dense embeddings blur
(product codes, "T1 2013", proper names). When a collection predates the
sparse upgrade, the store degrades that collection to dense-only until
`python -m tablerag.scripts.reindex_all` migrates it.
"""

from __future__ import annotations

from tablerag.models.registry import get_provider
from tablerag.query.pipeline import QueryContext
from tablerag.storage.qdrant import ALL_COLLECTIONS, get_vector_store


class Retrieve:
    def __init__(self, top_k: int = 50):
        self.top_k = top_k

    async def run(self, ctx: QueryContext) -> QueryContext:
        embedder = get_provider("embedder")
        # search on the standalone query: on a follow-up this is the condensed
        # question, so dense + sparse both see the full intent, not a fragment
        query = ctx.search_query
        [query_vector] = await embedder.embed([query])
        store = get_vector_store()
        hits = []
        for collection in ALL_COLLECTIONS:
            for hit in store.search(collection, query_vector.dense,
                                    ctx.routed_kb_ids, self.top_k,
                                    query_text=query):
                hit.payload["_collection"] = collection
                hits.append(hit)
        hits.sort(key=lambda h: h.score, reverse=True)
        ctx.hits = hits[:self.top_k]
        return ctx
