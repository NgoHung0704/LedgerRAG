"""Rerank step. Phase 1: pass-through (reranker role defaults to disabled).

Phase 4 plugs a model reranker (e.g. bge-reranker-v2-m3 behind an
openai_compat /rerank endpoint) into this slot: top-50 in, top-8 out.
"""

from __future__ import annotations

from tablerag.query.pipeline import QueryContext


class PassthroughRerank:
    async def run(self, ctx: QueryContext) -> QueryContext:
        return ctx
