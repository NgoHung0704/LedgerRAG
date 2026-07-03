"""Query pipeline: an explicit chain of pluggable steps (principle #4).

Router -> Retrieve -> Rerank -> AssembleContext -> Generate -> Verify

Every step is a class with `async run(ctx) -> ctx`. Phase 1 plugs:
SingleKBRouter (no-op), PassthroughRerank, Verify(disabled). Phase 4/5 swap
implementations without touching the chain.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol

from tablerag.core.config import get_settings
from tablerag.core.schemas import Citation
from tablerag.storage.qdrant import SearchHit
from tablerag.storage.repositories import ChunkContext


@dataclass
class QueryContext:
    kb_id: uuid.UUID
    question: str
    routed_kb_ids: list[uuid.UUID] = field(default_factory=list)
    hits: list[SearchHit] = field(default_factory=list)
    contexts: list[ChunkContext] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    answer: str = ""
    verification: dict | None = None


class Step(Protocol):
    async def run(self, ctx: QueryContext) -> QueryContext: ...


class QueryPipeline:
    def __init__(self, steps: list[Step]):
        self.steps = steps

    async def run(self, ctx: QueryContext) -> QueryContext:
        for step in self.steps:
            ctx = await step.run(ctx)
        return ctx

    async def stream(self, ctx: QueryContext) -> AsyncIterator[tuple[str, object]]:
        """Yields ("citations", list[Citation]) once context is assembled,
        then ("token", str) during generation, finally ("done", ctx)."""
        from tablerag.query.steps.generate import GenerateAnswer

        for step in self.steps:
            if isinstance(step, GenerateAnswer):
                yield "citations", ctx.citations
                async for token in step.stream(ctx):
                    yield "token", token
            else:
                ctx = await step.run(ctx)
        yield "done", ctx


def default_pipeline() -> QueryPipeline:
    from tablerag.query.steps.assemble import AssembleContext
    from tablerag.query.steps.generate import GenerateAnswer
    from tablerag.query.steps.rerank import PassthroughRerank
    from tablerag.query.steps.retrieve import Retrieve
    from tablerag.query.steps.router import SingleKBRouter
    from tablerag.query.steps.verify import Verify

    settings = get_settings()
    return QueryPipeline([
        SingleKBRouter(),          # Phase 5: LLMRouter plugs in here
        Retrieve(top_k=settings.retrieve_top_k),
        PassthroughRerank(),       # Phase 4: model reranker plugs in here
        AssembleContext(),
        GenerateAnswer(),
        Verify(enabled=settings.verification_enabled),  # Phase 4 fills this in
    ])
