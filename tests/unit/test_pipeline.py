import uuid

import pytest

from tablerag.core.schemas import Citation
from tablerag.query.pipeline import QueryContext, QueryPipeline
from tablerag.query.steps.generate import GenerateAnswer, build_context_block
from tablerag.query.steps.rerank import PassthroughRerank
from tablerag.query.steps.router import SingleKBRouter
from tablerag.query.steps.verify import Verify
from tablerag.storage.repositories import ChunkContext


class FakeChatProvider:
    def __init__(self, tokens):
        self.tokens = tokens
        self.calls: list[list] = []

    async def chat(self, messages, stream=True):
        self.calls.append(messages)
        for token in self.tokens:
            yield token


def make_ctx(with_context: bool = True) -> QueryContext:
    ctx = QueryContext(kb_id=uuid.uuid4(), question="Combien de jours de congés ?")
    if with_context:
        chunk = ChunkContext(
            chunk_id=uuid.uuid4(), text="Les cadres ont 25 jours de congés.",
            element_id=uuid.uuid4(), page=4, crop_image_path="crop.png",
            confidence=1.0, needs_review=False,
            doc_id=uuid.uuid4(), filename="reglement.pdf")
        ctx.contexts = [chunk]
        ctx.citations = [Citation(
            index=1, doc_id=chunk.doc_id, filename=chunk.filename, page=chunk.page,
            element_id=chunk.element_id, chunk_id=chunk.chunk_id,
            snippet=chunk.text, score=0.9)]
    return ctx


async def test_single_kb_router_routes_to_own_kb():
    ctx = make_ctx(with_context=False)
    await SingleKBRouter().run(ctx)
    assert ctx.routed_kb_ids == [ctx.kb_id]


async def test_generate_streams_and_accumulates_answer(monkeypatch):
    provider = FakeChatProvider(["Les cadres ", "ont 25 jours ", "[1]."])
    monkeypatch.setattr("tablerag.query.steps.generate.get_provider",
                        lambda role: provider)
    ctx = make_ctx()
    tokens = [t async for t in GenerateAnswer().stream(ctx)]
    assert "".join(tokens) == "Les cadres ont 25 jours [1]."
    assert ctx.answer == "Les cadres ont 25 jours [1]."
    # sources reached the prompt
    user_msg = provider.calls[0][-1]
    assert "reglement.pdf" in user_msg.content
    assert ctx.question in user_msg.content


async def test_generate_without_context_fails_honestly(monkeypatch):
    monkeypatch.setattr(
        "tablerag.query.steps.generate.get_provider",
        lambda role: pytest.fail("LLM must not be called without sources"))
    ctx = make_ctx(with_context=False)
    tokens = [t async for t in GenerateAnswer().stream(ctx)]
    assert tokens, "must still answer something"
    assert ctx.answer  # honest 'nothing found' message, no LLM involved


async def test_verify_disabled_is_pure_noop():
    ctx = make_ctx()
    result = await Verify(enabled=False).run(ctx)
    assert result is ctx
    assert ctx.verification is None


async def test_pipeline_stream_event_order(monkeypatch):
    provider = FakeChatProvider(["ok"])
    monkeypatch.setattr("tablerag.query.steps.generate.get_provider",
                        lambda role: provider)

    class SeedContext:
        """Stands in for Retrieve+Assemble without external services."""

        async def run(self, ctx):
            seeded = make_ctx()
            ctx.contexts, ctx.citations = seeded.contexts, seeded.citations
            return ctx

    pipeline = QueryPipeline([
        SingleKBRouter(), SeedContext(), PassthroughRerank(),
        GenerateAnswer(), Verify(enabled=False),
    ])
    events = [kind async for kind, _ in pipeline.stream(make_ctx(with_context=False))]
    assert events == ["citations", "token", "done"]


def test_context_block_numbers_sources():
    ctx = make_ctx()
    block = build_context_block(ctx)
    assert block.startswith("[1] (reglement.pdf, page 4)")
    assert "25 jours" in block
