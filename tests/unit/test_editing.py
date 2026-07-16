"""Manual element editing (Postgres side) + document purge helper.

The re-embedding half of indexing.reindex_element needs a live embedder +
Qdrant, so it's exercised by integration/eval, not here. These cover the
deterministic Postgres mutations and their guardrails."""

import uuid

from tablerag import indexing
from tablerag.storage import repositories as repo
from tablerag.storage.orm import Chunk, Record


def _seed_text(db_session):
    kb = repo.create_kb(db_session, "HR", "d")
    doc = repo.create_document(db_session, kb.id, "r.pdf", "kbs/x/y/o.pdf")
    el = repo.add_element(db_session, doc.id, page=1, bbox=[0, 0, 1, 1],
                          type_="text", crop_image_path="c.png", confidence=1.0)
    repo.add_chunks(db_session, el.id, [("old text one", 3), ("old two", 2)])
    return doc, el


def _seed_table(db_session):
    kb = repo.create_kb(db_session, "HR", "d")
    doc = repo.create_document(db_session, kb.id, "r.pdf", "kbs/x/y/o.pdf")
    el = repo.add_element(db_session, doc.id, page=1, bbox=[0, 0, 1, 1],
                          type_="table", crop_image_path="c.png",
                          needs_review=True)
    repo.add_table_element(db_session, el.id, "<table><tr><td>old</td></tr></table>",
                           "old summary", 1, 1, "vlm")
    repo.add_records(db_session, el.id, [
        {"dimensions": {"pays": "Maroc"}, "metrics": {"ca": 100},
         "raw_values": {"ca": "100"}, "text_repr": "Maroc | ca: 100"}])
    return doc, el


def test_edit_text_rechunks(db_session, monkeypatch):
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    _, el = _seed_text(db_session)
    ok = indexing.apply_element_edit(el.id, text="brand new corrected content")
    assert ok is True
    chunks = db_session.query(Chunk).filter(Chunk.element_id == el.id).all()
    assert len(chunks) == 1
    assert "brand new corrected" in chunks[0].text
    assert "old text one" not in chunks[0].text
    from tablerag.storage.orm import Element
    assert db_session.get(Element, el.id).meta["edited"] is True


def test_edit_table_updates_html_summary_records(db_session, monkeypatch):
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    _, el = _seed_table(db_session)
    ok = indexing.apply_element_edit(
        el.id, html="<table><tr><td>fixed</td></tr></table>",
        summary="corrected summary",
        records=[{"dimensions": {"pays": "France"}, "metrics": {"ca": 7462639},
                  "raw_values": {"ca": "7 462 639"}}])
    assert ok is True
    from tablerag.storage.orm import Element, TableElement
    table = db_session.get(TableElement, el.id)
    assert "fixed" in table.html
    assert table.summary == "corrected summary"
    records = db_session.query(Record).filter(
        Record.table_element_id == el.id).all()
    assert len(records) == 1
    assert records[0].dimensions == {"pays": "France"}
    assert records[0].metrics == {"ca": 7462639}
    assert "France" in records[0].text_repr and "7 462 639" in records[0].text_repr
    # editing clears the review flag
    assert db_session.get(Element, el.id).needs_review is False
    assert db_session.get(Element, el.id).meta["edited"] is True


def test_edit_missing_element_returns_false(db_session, monkeypatch):
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    assert indexing.apply_element_edit(uuid.uuid4(), text="x") is False


def test_document_view_reports_edited_flag(db_session):
    from tablerag.storage.orm import Element

    _, el = _seed_table(db_session)
    db_session.get(Element, el.id).meta = {"edited": True}
    db_session.flush()
    view = repo.get_document_view(db_session, el.doc_id)
    assert view[0]["edited"] is True


# -- helper: make indexing.apply_element_edit use the test session ------------

class _fake_scope:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        self.session.flush()
        return False
