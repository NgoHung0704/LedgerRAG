import uuid

from tablerag.storage import repositories as repo


def _seed_doc(s):
    kb = repo.create_kb(s, "HR", "Règlement intérieur")
    doc = repo.create_document(s, kb.id, "reglement.pdf", "kbs/x/docs/y/original.pdf")
    return kb, doc


def test_kb_crud(db_session):
    kb = repo.create_kb(db_session, "HR", "desc")
    assert repo.get_kb(db_session, kb.id) is not None
    assert [k.id for k in repo.list_kbs(db_session)] == [kb.id]


def test_get_or_create_kb_by_name(db_session):
    """Consume folder maps a subfolder name to a KB: reuse an existing one
    (case-insensitive) rather than duplicating; create when there's no match."""
    created = repo.get_or_create_kb_by_name(db_session, "ACCORDS")
    # a different-case name resolves to the same KB, not a second one
    again = repo.get_or_create_kb_by_name(db_session, "accords")
    assert again.id == created.id
    # a genuinely new name creates a new KB
    other = repo.get_or_create_kb_by_name(db_session, "DHR")
    assert other.id != created.id
    assert {k.name for k in repo.list_kbs(db_session)} == {"ACCORDS", "DHR"}


def test_document_status_transitions(db_session):
    _, doc = _seed_doc(db_session)
    assert doc.status == "queued"
    repo.set_document_status(db_session, doc.id, "parsing")
    repo.set_document_status(db_session, doc.id, "indexing", page_count=4)
    repo.set_document_status(db_session, doc.id, "done", page_count=4)
    refreshed = repo.get_document(db_session, doc.id)
    assert refreshed.status == "done"
    assert refreshed.page_count == 4

    repo.set_document_status(db_session, doc.id, "failed", error="Broken PDF")
    assert repo.get_document(db_session, doc.id).error == "Broken PDF"


def test_kb_document_status_counts(db_session):
    """The KB list's at-a-glance indicator: one grouped query returns each KB's
    document counts by status; KBs with no documents are simply absent."""
    kb_a = repo.create_kb(db_session, "A", "")
    kb_b = repo.create_kb(db_session, "B", "")
    repo.create_kb(db_session, "empty", "")  # no documents -> not in the map

    for status in ("done", "done", "parsing", "failed"):
        doc = repo.create_document(db_session, kb_a.id, "d.pdf", "k/d/o.pdf")
        repo.set_document_status(db_session, doc.id, status)
    doc_b = repo.create_document(db_session, kb_b.id, "d.pdf", "k/d/o.pdf")
    repo.set_document_status(db_session, doc_b.id, "done")

    counts = repo.kb_document_status_counts(db_session)
    assert counts[kb_a.id] == {"done": 2, "parsing": 1, "failed": 1}
    assert counts[kb_b.id] == {"done": 1}
    assert all(kb.name != "empty" or kb.id not in counts
               for kb in repo.list_kbs(db_session))


def test_delete_documents_bulk_and_cascade(db_session):
    """Bulk delete removes the chosen docs (and their elements/chunks cascade)
    in one call, leaves the rest, and reports the real count."""
    from tablerag.storage.orm import Chunk, Element

    kb = repo.create_kb(db_session, "HR", "")
    docs = []
    for i in range(3):
        doc = repo.create_document(db_session, kb.id, f"{i}.pdf", f"k/{i}/o.pdf")
        el = repo.add_element(db_session, doc.id, page=1, bbox=[0, 0, 1, 1],
                              type_="text", crop_image_path="c.png")
        repo.add_chunks(db_session, el.id, [("x", 1)])
        docs.append(doc)

    deleted = repo.delete_documents(db_session, [docs[0].id, docs[1].id])
    assert deleted == 2
    remaining = [d.id for d in repo.list_documents(db_session, kb.id)]
    assert remaining == [docs[2].id]
    # cascade reached elements + chunks of the deleted docs
    assert db_session.query(Element).count() == 1
    assert db_session.query(Chunk).count() == 1

    # empty input and unknown ids are no-ops, not errors
    assert repo.delete_documents(db_session, []) == 0
    assert repo.delete_documents(db_session, [uuid.uuid4()]) == 0


def test_reprocess_is_idempotent(db_session):
    """Phase 1 DoD: retry after a mid-job crash must not duplicate elements."""
    _, doc = _seed_doc(db_session)

    def ingest_once():
        repo.delete_doc_elements(db_session, doc.id)
        element = repo.add_element(
            db_session, doc.id, page=1, bbox=[0, 0, 100, 100], type_="text",
            crop_image_path="kbs/x/docs/y/pages/page-0001.png", confidence=1.0)
        repo.add_chunks(db_session, element.id, [("chunk a", 2), ("chunk b", 2)])
        return element

    ingest_once()
    element = ingest_once()  # simulated retry

    contexts = repo.get_chunk_contexts(
        db_session, [c.id for c in element.chunks])
    assert len(contexts) == 2

    from tablerag.storage.orm import Chunk, Element
    assert db_session.query(Element).count() == 1
    assert db_session.query(Chunk).count() == 2


def test_chunk_contexts_preserve_order_and_provenance(db_session):
    _, doc = _seed_doc(db_session)
    element = repo.add_element(
        db_session, doc.id, page=7, bbox=[0, 0, 10, 10], type_="text",
        crop_image_path="crop.png", confidence=0.9)
    rows = repo.add_chunks(db_session, element.id, [("one", 1), ("two", 1)])

    ordered = repo.get_chunk_contexts(db_session, [rows[1].id, rows[0].id])
    assert [c.text for c in ordered] == ["two", "one"]
    ctx = ordered[0]
    assert (ctx.page, ctx.filename, ctx.crop_image_path) == (
        7, "reglement.pdf", "crop.png")

    # unknown ids are silently dropped, not errors
    assert repo.get_chunk_contexts(db_session, [uuid.uuid4()]) == []


def test_review_flow_approve_and_unusable(db_session):
    """Phase 3 DoD: approve clears the flag; unusable keeps the image but
    excludes the element from retrieval (vector deletion is the API's job)."""
    _, doc = _seed_doc(db_session)
    element = repo.add_element(
        db_session, doc.id, page=1, bbox=[0, 0, 10, 10], type_="table",
        crop_image_path="crop.png", needs_review=True,
        meta={"confidence_detail": {"signals": {"agreement": 0.5}}})

    approved = repo.approve_element(db_session, element.id)
    assert approved.needs_review is False
    assert approved.meta["reviewed"] == "approved"
    assert approved.meta["confidence_detail"]  # detail kept for audit

    unusable = repo.mark_element_unusable(db_session, element.id)
    assert unusable.meta["unusable"] is True
    assert unusable.needs_review is False

    assert repo.approve_element(db_session, __import__("uuid").uuid4()) is None


def test_chat_session_and_messages(db_session):
    kb, _ = _seed_doc(db_session)
    session = repo.get_or_create_session(db_session, kb.id, None)
    again = repo.get_or_create_session(db_session, kb.id, session.id)
    assert again.id == session.id

    msg = repo.add_message(db_session, session.id, "assistant", "Bonjour",
                           citations=[{"index": 1}])
    assert msg.citations == [{"index": 1}]


def test_recent_messages_order_and_limit(db_session):
    """Multi-turn history must come back oldest→newest so a follow-up condenses
    against the real order — even when a turn's user+assistant rows share a
    transaction (created_at set explicitly here to pin the ordering)."""
    from datetime import datetime, timedelta, timezone

    from tablerag.storage.orm import ChatMessage

    kb, _ = _seed_doc(db_session)
    session = repo.get_or_create_session(db_session, kb.id, None)
    t0 = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
    turns = [("user", "Q1"), ("assistant", "A1"),
             ("user", "Q2"), ("assistant", "A2")]
    for i, (role, content) in enumerate(turns):
        db_session.add(ChatMessage(session_id=session.id, role=role,
                                   content=content,
                                   created_at=t0 + timedelta(seconds=i)))
    db_session.flush()

    assert repo.get_recent_messages(db_session, session.id) == turns
    # limit keeps the most recent, still oldest→newest
    assert repo.get_recent_messages(db_session, session.id, limit=2) == [
        ("user", "Q2"), ("assistant", "A2")]
    # an unknown / brand-new session has no history
    assert repo.get_recent_messages(db_session, uuid.uuid4()) == []
