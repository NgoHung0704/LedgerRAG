"""VectorStore wiring — the parts we can check without a live Qdrant."""

import uuid

from tablerag.core.config import get_settings


def test_vector_store_passes_explicit_timeout(monkeypatch):
    """Regression for the bulk-upload failure: the client must be built with an
    explicit timeout, not the library's 5s default that a concurrent upload of
    many documents trips (ResponseHandlingException: timed out)."""
    import tablerag.storage.qdrant as qmod

    captured: dict = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(qmod, "QdrantClient", FakeClient)

    qmod.VectorStore(url="http://qdrant:6333")

    assert captured["url"] == "http://qdrant:6333"
    assert captured["timeout"] == get_settings().qdrant_timeout
    assert captured["timeout"] >= 60  # comfortably above the 5s default


def test_delete_docs_is_batched_one_call_per_collection(monkeypatch):
    """Regression for the bulk-delete 'NetworkError': deleting many documents
    must issue ONE MatchAny filtered delete per collection, not per document."""
    import tablerag.storage.qdrant as qmod
    from qdrant_client import models as qm

    deletes: list[str] = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def collection_exists(self, name):
            return True

        def delete(self, *, collection_name, points_selector, wait):
            deletes.append(collection_name)
            # the filter must match ANY of the given doc_ids (batched), not one
            cond = points_selector.filter.must[0]
            assert cond.key == "doc_id"
            assert isinstance(cond.match, qm.MatchAny)
            assert len(cond.match.any) == 40  # all docs in a single condition

    monkeypatch.setattr(qmod, "QdrantClient", FakeClient)
    store = qmod.VectorStore(url="http://qdrant:6333")

    store.delete_docs([uuid.uuid4() for _ in range(40)])

    # exactly one delete per collection — 3 calls total, not 40×3
    assert sorted(deletes) == sorted(qmod.ALL_COLLECTIONS)

    # empty input touches nothing
    deletes.clear()
    store.delete_docs([])
    assert deletes == []
