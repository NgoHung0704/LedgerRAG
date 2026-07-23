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
