"""Document deletion cascades in Postgres, and object-store prefix delete."""

from tablerag.storage import repositories as repo
from tablerag.storage.object_store import LocalFSStore, doc_prefix
from tablerag.storage.orm import Chunk, Element, Record, TableElement


def test_delete_document_cascades(db_session):
    kb = repo.create_kb(db_session, "HR", "desc")
    doc = repo.create_document(db_session, kb.id, "r.pdf", "kbs/x/docs/y/original.pdf")
    element = repo.add_element(db_session, doc.id, page=1, bbox=[0, 0, 1, 1],
                               type_="table", crop_image_path="c.png")
    repo.add_chunks(db_session, element.id, [("t", 1)])
    repo.add_table_element(db_session, element.id, "<table/>", None, 1, 1, "vlm")
    repo.add_records(db_session, element.id, [
        {"dimensions": {"a": "x"}, "metrics": {"m": 1}, "raw_values": {"m": "1"},
         "text_repr": "x | m: 1"}])

    kb_id = repo.delete_document(db_session, doc.id)
    assert kb_id == kb.id
    assert repo.get_document(db_session, doc.id) is None
    for model in (Element, Chunk, TableElement, Record):
        assert db_session.query(model).count() == 0
    # the KB itself survives
    assert repo.get_kb(db_session, kb.id) is not None


def test_delete_missing_document_returns_none(db_session):
    import uuid
    assert repo.delete_document(db_session, uuid.uuid4()) is None


def test_object_store_delete_prefix(tmp_path):
    store = LocalFSStore(str(tmp_path))
    prefix = doc_prefix("kb1", "doc1")
    store.put(f"{prefix}/original.pdf", b"pdf")
    store.put(f"{prefix}/pages/page-0001.png", b"img")
    store.put("kbs/kb1/docs/doc2/original.pdf", b"other")

    store.delete_prefix(prefix)
    assert not store.exists(f"{prefix}/original.pdf")
    assert not store.exists(f"{prefix}/pages/page-0001.png")
    # a sibling document is untouched
    assert store.exists("kbs/kb1/docs/doc2/original.pdf")
