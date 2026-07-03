"""Router step: chooses which KB(s) to query.

KB isolation + routing is the product's founding idea (SPEC §2 design note).
Phase 1 ships the no-op SingleKBRouter; Phase 5 adds an LLMRouter that reads
the question plus every kb.description and may select several KBs. Everything
downstream already filters by `routed_kb_ids`, so that swap is plug-in only.
"""

from __future__ import annotations

from tablerag.query.pipeline import QueryContext


class SingleKBRouter:
    async def run(self, ctx: QueryContext) -> QueryContext:
        ctx.routed_kb_ids = [ctx.kb_id]
        return ctx
