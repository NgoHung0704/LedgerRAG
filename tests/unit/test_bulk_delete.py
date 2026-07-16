"""Bulk document deletion: repository cascade + KB-scoping of the endpoint."""

import uuid

from tablerag.storage import repositories as repo
from tablerag.storage.orm import Document


def test_delete_only_targets_owned_documents(db_session):
    """The endpoint filters doc_ids to those owned by the KB; verify the
    repository-level building blocks it relies on."""
    kb_a = repo.create_kb(db_session, "A", "d")
    kb_b = repo.create_kb(db_session, "B", "d")
    a1 = repo.create_document(db_session, kb_a.id, "a1.pdf", "k")
    a2 = repo.create_document(db_session, kb_a.id, "a2.pdf", "k")
    b1 = repo.create_document(db_session, kb_b.id, "b1.pdf", "k")

    owned = {d.id for d in repo.list_documents(db_session, kb_a.id)}
    assert owned == {a1.id, a2.id}
    assert b1.id not in owned  # cross-KB id would be ignored by the route

    for doc_id in (a1.id, a2.id):
        assert repo.delete_document(db_session, doc_id) == kb_a.id
    assert db_session.query(Document).count() == 1  # only b1 remains
    assert repo.get_document(db_session, b1.id) is not None


def test_delete_unknown_returns_none(db_session):
    assert repo.delete_document(db_session, uuid.uuid4()) is None
