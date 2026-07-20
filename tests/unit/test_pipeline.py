import uuid

import pytest

from tablerag.core.schemas import Citation
from tablerag.query.pipeline import QueryContext, QueryPipeline, SourceBlock
from tablerag.query.steps.generate import GenerateAnswer, build_context_block
from tablerag.query.steps.rerank import PassthroughRerank
from tablerag.query.steps.router import SingleKBRouter
from tablerag.query.steps.verify import Verify


class FakeChatProvider:
    def __init__(self, tokens):
        self.tokens = tokens
        self.calls: list[list] = []

    async def chat(self, messages, stream=True, temperature=None, options=None):
        self.calls.append(messages)
        for token in self.tokens:
            yield token


def _block(kind="text", content="Les cadres ont 25 jours de congés.",
           needs_review=False) -> SourceBlock:
    return SourceBlock(
        kind=kind, doc_id=uuid.uuid4(), filename="reglement.pdf", page=4,
        element_id=uuid.uuid4(), chunk_id=uuid.uuid4() if kind == "text" else None,
        content=content, snippet=content[:240], score=0.9,
        crop_image_path="crop.png", confidence=1.0, needs_review=needs_review)


def make_ctx(*blocks: SourceBlock) -> QueryContext:
    ctx = QueryContext(kb_id=uuid.uuid4(), question="Combien de jours de congés ?")
    ctx.sources = list(blocks)
    ctx.citations = [
        Citation(index=i + 1, kind=b.kind, doc_id=b.doc_id, filename=b.filename,
                 page=b.page, element_id=b.element_id, chunk_id=b.chunk_id,
                 snippet=b.snippet, score=b.score, needs_review=b.needs_review)
        for i, b in enumerate(blocks)
    ]
    return ctx


async def test_single_kb_router_routes_to_own_kb():
    ctx = make_ctx()
    await SingleKBRouter().run(ctx)
    assert ctx.routed_kb_ids == [ctx.kb_id]


async def test_generate_streams_and_accumulates_answer(monkeypatch):
    provider = FakeChatProvider(["Les cadres ", "ont 25 jours ", "[1]."])
    monkeypatch.setattr("tablerag.query.steps.generate.get_provider",
                        lambda role: provider)
    ctx = make_ctx(_block())
    tokens = [t async for t in GenerateAnswer().stream(ctx)]
    assert "".join(tokens) == "Les cadres ont 25 jours [1]."
    assert ctx.answer == "Les cadres ont 25 jours [1]."
    user_msg = provider.calls[0][-1]
    assert "reglement.pdf" in user_msg.content
    assert ctx.question in user_msg.content


async def test_generate_without_context_fails_honestly(monkeypatch):
    monkeypatch.setattr(
        "tablerag.query.steps.generate.get_provider",
        lambda role: pytest.fail("LLM must not be called without sources"))
    ctx = make_ctx()
    tokens = [t async for t in GenerateAnswer().stream(ctx)]
    assert tokens, "must still answer something"
    assert ctx.answer  # honest 'nothing found' message, no LLM involved


async def test_verify_disabled_is_pure_noop():
    ctx = make_ctx(_block())
    result = await Verify(enabled=False).run(ctx)
    assert result is ctx
    assert ctx.verification is None


async def test_pipeline_stream_event_order(monkeypatch):
    provider = FakeChatProvider(["ok"])
    monkeypatch.setattr("tablerag.query.steps.generate.get_provider",
                        lambda role: provider)
    # keep the Rerank step off the network/DB in unit tests
    monkeypatch.setattr(
        "tablerag.query.steps.rerank.effective_config",
        lambda role: type("Cfg", (), {"provider": "disabled"})())

    class SeedContext:
        """Stands in for Retrieve+Assemble without external services."""

        async def run(self, ctx):
            seeded = make_ctx(_block())
            ctx.sources, ctx.citations = seeded.sources, seeded.citations
            return ctx

    pipeline = QueryPipeline([
        SingleKBRouter(), SeedContext(),
        PassthroughRerank(fallback_top_k=12),
        GenerateAnswer(), Verify(enabled=False),
    ])
    events = [kind async for kind, _ in pipeline.stream(make_ctx())]
    assert events == ["citations", "token", "done"]


def test_context_block_numbers_sources():
    ctx = make_ctx(_block())
    block = build_context_block(ctx)
    assert block.startswith("[1] (reglement.pdf, page 4)")
    assert "25 jours" in block


def test_context_block_marks_tables_and_low_confidence():
    table_html = "<table><tr><th>Poste</th><th>T1</th></tr></table>"
    ctx = make_ctx(
        _block(),
        _block(kind="table", content=table_html, needs_review=True))
    block = build_context_block(ctx)
    assert "[2] (reglement.pdf, page 4, table)" in block
    assert "LOW CONFIDENCE" in block
    assert table_html in block


# --- matched-row highlighting (run 2: values read off the wrong row/table) ---

def _table_source(**over):
    from tablerag.storage.repositories import TableSource

    base = dict(element_id=uuid.uuid4(), doc_id=uuid.uuid4(),
                filename="Cotation.pdf", page=1,
                html="<table><tr><td>16</td><td>52 à 54</td></tr></table>",
                summary="Grille de cotation des emplois",
                crop_image_path="k", confidence=0.99, needs_review=False)
    base.update(over)
    return TableSource(**base)


def test_table_block_surfaces_matched_rows_before_the_grid():
    from tablerag.query.steps.assemble import AssembleContext

    table = _table_source()
    block = AssembleContext._table_block(
        table, {table.element_id: 0.9},
        ["Cotations: 52 à 54 | Classes: 16 | Groupes: H"])
    assert "Rows matching the question:" in block.content
    # the needle must come before the haystack so a small model reads it first
    assert block.content.index("52 à 54") < block.content.index("<table>")
    assert "Grille de cotation" in block.content  # summary still leads


def test_table_block_without_matched_rows_is_unchanged():
    from tablerag.query.steps.assemble import AssembleContext

    table = _table_source()
    block = AssembleContext._table_block(table, {table.element_id: 0.5})
    assert "Rows matching" not in block.content
    assert block.content.startswith("Table summary:")


def test_unparsed_table_still_reports_image_only():
    from tablerag.query.steps.assemble import AssembleContext

    table = _table_source(html=None, summary=None)
    block = AssembleContext._table_block(table, {})
    assert "could not be parsed" in block.content
