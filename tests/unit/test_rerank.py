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


# --- document diversification (run 4: right doc retrieved but buried) --------

class _Hit:
    def __init__(self, doc, score):
        self.payload = {"doc_id": doc}
        self.score = score

    def __repr__(self):
        return f"{self.payload['doc_id']}@{self.score}"


def _docs(hits):
    return [h.payload["doc_id"] for h in hits]


def test_diversify_promotes_each_documents_best_block():
    from tablerag.query.steps.rerank import diversify_by_document

    # the shape measured on the box: one long document owns the head, and the
    # document holding the answer sits at rank 5
    hits = [_Hit("avenant", 9), _Hit("avenant", 8), _Hit("avenant", 7),
            _Hit("avenant", 6), _Hit("cetiat", 5), _Hit("glossaire", 4),
            _Hit("avenant", 3)]
    out = diversify_by_document(hits, 12)
    assert _docs(out)[:3] == ["avenant", "cetiat", "glossaire"]
    # nothing is dropped when k is large enough
    assert len(out) == len(hits)


def test_diversify_preserves_order_within_a_document():
    from tablerag.query.steps.rerank import diversify_by_document

    hits = [_Hit("a", 9), _Hit("a", 8), _Hit("b", 7), _Hit("a", 6)]
    out = diversify_by_document(hits, 12)
    a_scores = [h.score for h in out if h.payload["doc_id"] == "a"]
    assert a_scores == [9, 8, 6]  # never reordered inside a document


def test_diversify_respects_k_and_handles_missing_doc_id():
    from tablerag.query.steps.rerank import diversify_by_document

    hits = [_Hit("a", 9), _Hit("b", 8), _Hit("c", 7)]
    assert len(diversify_by_document(hits, 2)) == 2
    orphan = _Hit("x", 1)
    orphan.payload = {}
    assert diversify_by_document([orphan], 5) == [orphan]
    assert diversify_by_document([], 5) == []


def test_single_document_pool_is_untouched():
    from tablerag.query.steps.rerank import diversify_by_document

    hits = [_Hit("a", 9), _Hit("a", 8), _Hit("a", 7)]
    assert diversify_by_document(hits, 12) == hits
