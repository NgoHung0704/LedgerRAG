"""Phase 5: the KB-level review queue surfaces flagged, still-usable elements
newest-doc-first, and drops anything marked unusable."""

import uuid

from tablerag.storage import repositories as repo


def _table(db, doc_id, page, *, needs_review, unusable=False):
    meta = {"unusable": True} if unusable else {}
    el = repo.add_element(db, doc_id, page=page, bbox=[0, 0, 1, 1],
                          type_="table", crop_image_path="c.png",
                          confidence=0.2 if needs_review else 1.0,
                          needs_review=needs_review, meta=meta)
    repo.add_table_element(db, el.id, "<table/>", None, 1, 1, "vlm")
    return el


def test_review_queue_lists_only_flagged_and_usable(db_session):
    kb = repo.create_kb(db_session, "HR", "desc")
    doc = repo.create_document(db_session, kb.id, "cotation.pdf", "k/x/o.pdf")
    flagged = _table(db_session, doc.id, 1, needs_review=True)
    _table(db_session, doc.id, 2, needs_review=False)              # clean
    _table(db_session, doc.id, 3, needs_review=True, unusable=True)  # excluded

    items = repo.needs_review_elements(db_session, kb.id)
    assert [it["element_id"] for it in items] == [flagged.id]
    assert items[0]["filename"] == "cotation.pdf"
    assert items[0]["page"] == 1


def test_review_queue_empty_for_clean_kb(db_session):
    kb = repo.create_kb(db_session, "Clean", "desc")
    doc = repo.create_document(db_session, kb.id, "ok.pdf", "k/x/o.pdf")
    _table(db_session, doc.id, 1, needs_review=False)
    assert repo.needs_review_elements(db_session, kb.id) == []


def test_review_queue_scoped_to_its_kb(db_session):
    kb_a = repo.create_kb(db_session, "A", "d")
    kb_b = repo.create_kb(db_session, "B", "d")
    doc_a = repo.create_document(db_session, kb_a.id, "a.pdf", "k/a/o.pdf")
    doc_b = repo.create_document(db_session, kb_b.id, "b.pdf", "k/b/o.pdf")
    _table(db_session, doc_a.id, 1, needs_review=True)
    _table(db_session, doc_b.id, 1, needs_review=True)
    assert len(repo.needs_review_elements(db_session, kb_a.id)) == 1
    assert repo.needs_review_elements(db_session, kb_a.id)[0]["filename"] == "a.pdf"
