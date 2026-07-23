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


@dataclass
class SourceBlock:
    """One evidence unit handed to the LLM: a text chunk or a whole table
    (record/summary hits always pull the parent table, SPEC Phase 2 §6)."""

    kind: str  # 'text' | 'table'
    doc_id: uuid.UUID
    filename: str
    page: int
    element_id: uuid.UUID
    content: str  # chunk text, or table HTML (+ summary line)
    snippet: str
    score: float
    chunk_id: uuid.UUID | None = None
    crop_image_path: str | None = None
    confidence: float | None = None
    needs_review: bool = False


@dataclass
class QueryContext:
    kb_id: uuid.UUID
    question: str
    locale: str | None = None  # KB declared locale, for number verification
    # Phase 5 routing: pinned_kb_ids is the user's manual override (search
    # exactly these); when None the LLMRouter picks. routed_kb_ids is the
    # resolved set everything downstream filters by. routing records the
    # decision (mode + chosen KBs) for the chat_message log and eval-routing.
    pinned_kb_ids: list[uuid.UUID] | None = None
    routed_kb_ids: list[uuid.UUID] = field(default_factory=list)
    routing: dict | None = None
    hits: list[SearchHit] = field(default_factory=list)
    sources: list[SourceBlock] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    answer: str = ""
    verification: dict | None = None
    # Multi-turn: prior turns (role, content) oldest→newest, excluding the
    # current question. CondenseQuestion folds them into search_question — a
    # standalone query router+retrieval act on — while the answer still draws
    # facts only from freshly retrieved sources (history is context, not a source).
    history: list[tuple[str, str]] = field(default_factory=list)
    search_question: str = ""

    @property
    def search_query(self) -> str:
        """The query router and retrieval search on: the condensed standalone
        question when a follow-up had history to resolve, else the raw one."""
        return self.search_question or self.question


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


def default_pipeline(verify: bool | None = None, *,
                     router: object | None = None) -> QueryPipeline:
    from tablerag.query.steps.assemble import AssembleContext
    from tablerag.query.steps.condense import CondenseQuestion
    from tablerag.query.steps.generate import GenerateAnswer
    from tablerag.query.steps.rerank import Rerank
    from tablerag.query.steps.retrieve import Retrieve
    from tablerag.query.steps.router import SingleKBRouter
    from tablerag.query.steps.verify import Verify

    settings = get_settings()
    enabled = settings.verification_enabled if verify is None else verify
    # CondenseQuestion runs first so router+retrieval see a standalone query on
    # follow-ups; it is a pure passthrough with no history (single-turn evals
    # are byte-identical). Phase 1 scoped chat pins one KB (SingleKBRouter);
    # Phase 5 multi-KB chat passes an LLMRouter. Same slot — principle #4.
    return QueryPipeline([
        CondenseQuestion(),
        router or SingleKBRouter(),
        Retrieve(top_k=settings.retrieve_candidates),
        Rerank(top_k=settings.rerank_top_k,
               fallback_top_k=settings.retrieve_top_k),
        AssembleContext(),
        GenerateAnswer(),
        Verify(enabled=enabled),
    ])
