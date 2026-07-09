"""Verify step: answer-number verification (Phase 4).

The pluggable slot has existed since Phase 1 as a no-op; Phase 4 fills it.
When disabled it is a clean no-op with zero side effects (Phase 4 DoD).
When enabled it cross-checks every number in the answer against the numbers
in the retrieved context and records the result in ctx.verification for the
frontend to badge.
"""

from __future__ import annotations

from tablerag.query.pipeline import QueryContext
from tablerag.query.verification import verify_answer


class Verify:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    async def run(self, ctx: QueryContext) -> QueryContext:
        if not self.enabled:
            return ctx
        if not ctx.answer or not ctx.sources:
            ctx.verification = {"enabled": True, "status": "ok",
                                "numbers": [], "unverified": []}
            return ctx
        source_texts = [b.content for b in ctx.sources]
        result = verify_answer(ctx.answer, source_texts, ctx.locale)
        ctx.verification = result.to_dict()
        return ctx
