"""Bulk-upload reliability: a transient Qdrant timeout is retried at the write
itself (so the ingest task doesn't re-parse the whole document), and large
upserts are split into batches so each request stays small under load."""

import uuid

import pytest
from qdrant_client.http.exceptions import ResponseHandlingException

import tablerag.storage.qdrant as q


def test_retry_qdrant_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(q.time, "sleep", lambda *_: None)  # no real backoff
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ResponseHandlingException("timed out")
        return "ok"

    assert q._retry_qdrant(op, "test") == "ok"
    assert calls["n"] == 3


def test_retry_qdrant_gives_up_after_the_cap(monkeypatch):
    monkeypatch.setattr(q.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise ResponseHandlingException("timed out")

    with pytest.raises(ResponseHandlingException):
        q._retry_qdrant(op, "test")
    assert calls["n"] == q._QDRANT_ATTEMPTS  # tried, then surfaced


def test_upsert_splits_large_point_sets_into_batches():
    store = q.VectorStore.__new__(q.VectorStore)  # skip real client construction
    store.dim = 3
    store._sparse_ready = {}
    sizes: list[int] = []

    class FakeClient:
        def upsert(self, collection_name, points, wait):
            sizes.append(len(points))

    store.client = FakeClient()
    n = q._UPSERT_BATCH + 10
    ids = [uuid.uuid4() for _ in range(n)]
    store.upsert("chunks", ids=ids, dense=[[0.0, 0.0, 0.0]] * n,
                 payloads=[{} for _ in range(n)], texts=None)

    assert sum(sizes) == n            # every point written
    assert len(sizes) == 2            # split into two requests
    assert sizes[0] == q._UPSERT_BATCH


def test_upsert_retries_a_transient_timeout(monkeypatch):
    monkeypatch.setattr(q.time, "sleep", lambda *_: None)
    store = q.VectorStore.__new__(q.VectorStore)
    store.dim = 3
    store._sparse_ready = {}
    attempts = {"n": 0}

    class FlakyClient:
        def upsert(self, collection_name, points, wait):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ResponseHandlingException("timed out")

    store.client = FlakyClient()
    store.upsert("chunks", ids=[uuid.uuid4()], dense=[[0.0, 0.0, 0.0]],
                 payloads=[{}], texts=None)
    assert attempts["n"] == 2  # first timed out, retried, succeeded
