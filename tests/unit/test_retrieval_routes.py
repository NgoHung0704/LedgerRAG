"""The other prefix the auth middleware lets through without an identity.

Same shape as tests/unit/test_embed_routes.py: most of what matters here is
what a missing/wrong key CANNOT do, plus that a valid key gets back the Dify
External Knowledge API record shape.
"""

import contextlib
import uuid

import pytest
from fastapi.testclient import TestClient

from tablerag.api.main import create_app
from tablerag.core.auth import OPEN_PREFIXES


def retrieval_paths() -> list[str]:
    paths = create_app().openapi()["paths"]
    return [p for p in paths if p.startswith("/api/retrieval")]


@pytest.fixture
def client(monkeypatch):
    """A client whose retrieval route finds no KB, without a database."""
    from tablerag.api.routes import retrieval

    @contextlib.contextmanager
    def no_database():
        yield None

    monkeypatch.setattr(retrieval, "session_scope", no_database)
    monkeypatch.setattr(retrieval.repo, "get_kb_by_retrieval_key",
                        lambda s, key: None)
    return TestClient(create_app())


def test_the_retrieval_prefix_is_open_at_the_middleware():
    assert "/api/retrieval" in OPEN_PREFIXES


def test_every_retrieval_route_carries_a_kb_id():
    paths = retrieval_paths()
    assert paths, "no retrieval routes registered"
    for path in paths:
        assert "{kb_id}" in path, f"{path} is under the open prefix but takes no kb_id"


def test_an_unknown_key_is_not_found(client):
    kb_id = uuid.uuid4()
    r = client.post(f"/api/retrieval/{kb_id}/retrieval",
                    headers={"Authorization": "Bearer nope"},
                    json={"query": "hello"})
    assert r.status_code == 404
    assert r.json()["error_code"] == 1002


def test_a_missing_authorization_header_is_not_found(client):
    kb_id = uuid.uuid4()
    r = client.post(f"/api/retrieval/{kb_id}/retrieval", json={"query": "hello"})
    assert r.status_code == 404


def test_a_valid_key_returns_records(monkeypatch):
    from tablerag.api.routes import retrieval
    from tablerag.core.schemas import Citation
    from tablerag.query.pipeline import QueryContext, SourceBlock
    from tablerag.storage.orm import KnowledgeBase

    kb_id = uuid.uuid4()
    kb = KnowledgeBase(id=kb_id, name="HR", description="",
                       config={"retrieval_key": "key_abc"})

    @contextlib.contextmanager
    def no_database():
        yield None

    monkeypatch.setattr(retrieval, "session_scope", no_database)
    monkeypatch.setattr(retrieval.repo, "get_kb_by_retrieval_key",
                        lambda s, key: kb if key == "key_abc" else None)

    class FakeStep:
        def __init__(self, **_kwargs):
            pass

        async def run(self, ctx: QueryContext) -> QueryContext:
            return ctx

    class FakeAssemble:
        async def run(self, ctx: QueryContext) -> QueryContext:
            doc_id, element_id = uuid.uuid4(), uuid.uuid4()
            ctx.citations = [
                Citation(index=1, doc_id=doc_id, filename="policy.pdf", page=3,
                        element_id=element_id, snippet="s", score=0.9),
                Citation(index=2, doc_id=doc_id, filename="policy.pdf", page=5,
                        element_id=uuid.uuid4(), snippet="s", score=0.1),
            ]
            ctx.sources = [
                SourceBlock(kind="text", doc_id=doc_id, filename="policy.pdf",
                           page=3, element_id=element_id, content="full text",
                           snippet="s", score=0.9),
                SourceBlock(kind="text", doc_id=doc_id, filename="policy.pdf",
                           page=5, element_id=uuid.uuid4(), content="low score",
                           snippet="s", score=0.1),
            ]
            return ctx

    monkeypatch.setattr(retrieval, "SingleKBRouter", FakeStep)
    monkeypatch.setattr(retrieval, "Retrieve", FakeStep)
    monkeypatch.setattr(retrieval, "Rerank", FakeStep)
    monkeypatch.setattr(retrieval, "AssembleContext", FakeAssemble)

    client = TestClient(create_app())
    r = client.post(f"/api/retrieval/{kb_id}/retrieval",
                    headers={"Authorization": "Bearer key_abc"},
                    json={"query": "what is the policy?",
                          "retrieval_setting": {"top_k": 5, "score_threshold": 0.5}})
    assert r.status_code == 200
    records = r.json()["records"]
    # score_threshold=0.5 drops the second (score 0.1) source
    assert len(records) == 1
    assert records[0]["content"] == "full text"
    assert records[0]["score"] == 0.9
    assert records[0]["title"] == "policy.pdf (p.3)"
    assert records[0]["metadata"]["page"] == 3
