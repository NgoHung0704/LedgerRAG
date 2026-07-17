"""Rerank step: disabled -> truncate; enabled -> provider order; failure ->
honest degradation to retrieval order."""

import uuid

import pytest

from tablerag.query.pipeline import QueryContext
from tablerag.query.steps import rerank as rerank_mod
from tablerag.query.steps.rerank import Rerank
from tablerag.storage.qdrant import SearchHit


def _hits(n: int) -> list[SearchHit]:
    return [SearchHit(id=uuid.uuid4(), score=1.0 - i / 100,
                      payload={"_collection": "chunks",
                               "chunk_id": str(uuid.uuid4())})
            for i in range(n)]


def _ctx(n_hits: int) -> QueryContext:
    ctx = QueryContext(kb_id=uuid.uuid4(), question="q")
    ctx.hits = _hits(n_hits)
    return ctx


class _Cfg:
    def __init__(self, provider):
        self.provider = provider


async def test_disabled_role_truncates_to_fallback(monkeypatch):
    monkeypatch.setattr(rerank_mod, "effective_config",
                        lambda role: _Cfg("disabled"))
    ctx = _ctx(50)
    await Rerank(top_k=8, fallback_top_k=12).run(ctx)
    assert len(ctx.hits) == 12


async def test_enabled_role_orders_by_provider_scores(monkeypatch):
    monkeypatch.setattr(rerank_mod, "effective_config",
                        lambda role: _Cfg("openai_compat"))

    class FakeReranker:
        async def rerank(self, query, docs):
            # reverse order: last doc most relevant
            return [float(i) for i in range(len(docs))]

    monkeypatch.setattr(rerank_mod, "get_provider", lambda role: FakeReranker())
    ctx = _ctx(10)
    original = list(ctx.hits)
    monkeypatch.setattr(Rerank, "_fetch_texts",
                        staticmethod(lambda hits: [f"doc {i}" for i in
                                                   range(len(hits))]))
    await Rerank(top_k=3, fallback_top_k=12).run(ctx)
    assert len(ctx.hits) == 3
    assert ctx.hits[0].id == original[-1].id  # highest provider score first


async def test_provider_failure_degrades_to_retrieval_order(monkeypatch):
    monkeypatch.setattr(rerank_mod, "effective_config",
                        lambda role: _Cfg("openai_compat"))

    class BrokenReranker:
        async def rerank(self, query, docs):
            raise ConnectionError("endpoint down")

    monkeypatch.setattr(rerank_mod, "get_provider",
                        lambda role: BrokenReranker())
    monkeypatch.setattr(Rerank, "_fetch_texts",
                        staticmethod(lambda hits: ["x"] * len(hits)))
    ctx = _ctx(50)
    original_first = ctx.hits[0].id
    await Rerank(top_k=8, fallback_top_k=12).run(ctx)
    assert len(ctx.hits) == 12
    assert ctx.hits[0].id == original_first  # retrieval order preserved


async def test_empty_hits_are_fine(monkeypatch):
    monkeypatch.setattr(rerank_mod, "effective_config",
                        lambda role: _Cfg("disabled"))
    ctx = _ctx(0)
    await Rerank().run(ctx)
    assert ctx.hits == []
