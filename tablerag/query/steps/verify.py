"""Verify step: the answer-verification plug (principle #4).

Phase 1: the slot exists but is disabled — `run` is a clean no-op with zero
side effects (Phase 4 DoD requires exactly that when toggled off). Phase 4
implements it: extract every number from the answer (locale-aware, reusing
core/numbers.py), check each against the records/raw_values in context, allow
whitelisted simple arithmetic, and flag anything unverifiable.
"""

from __future__ import annotations

from tablerag.query.pipeline import QueryContext


class Verify:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    async def run(self, ctx: QueryContext) -> QueryContext:
        if not self.enabled:
            return ctx
        # Phase 4: number extraction + source cross-check lands here.
        ctx.verification = {"status": "not_implemented"}
        return ctx
