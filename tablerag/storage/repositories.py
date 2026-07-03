"""Repository functions — the only way either pipeline touches Postgres."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from tablerag.storage.orm import (
    ChatMessage,
    ChatSession,
    Chunk,
    Document,
    Element,
    KnowledgeBase,
)

# ---------------------------------------------------------------- knowledge base

def create_kb(s: Session, name: str, description: str = "",
              config: dict | None = None) -> KnowledgeBase:
    kb = KnowledgeBase(name=name, description=description, config=config or {})
    s.add(kb)
    s.flush()
    return kb


def get_kb(s: Session, kb_id: uuid.UUID) -> KnowledgeBase | None:
    return s.get(KnowledgeBase, kb_id)


def list_kbs(s: Session) -> list[KnowledgeBase]:
    return list(s.scalars(select(KnowledgeBase).order_by(KnowledgeBase.created_at)))


# ---------------------------------------------------------------- documents

def create_document(s: Session, kb_id: uuid.UUID, filename: str,
                    file_path: str, doc_id: uuid.UUID | None = None) -> Document:
    doc = Document(id=doc_id or uuid.uuid4(), kb_id=kb_id, filename=filename,
                   file_path=file_path, status="queued")
    s.add(doc)
    s.flush()
    return doc


def get_document(s: Session, doc_id: uuid.UUID) -> Document | None:
    return s.get(Document, doc_id)


def list_documents(s: Session, kb_id: uuid.UUID) -> list[Document]:
    return list(s.scalars(
        select(Document).where(Document.kb_id == kb_id)
        .order_by(Document.created_at.desc())))


def set_document_status(s: Session, doc_id: uuid.UUID, status: str,
                        error: str | None = None,
                        page_count: int | None = None) -> None:
    doc = s.get(Document, doc_id)
    if doc is None:
        raise LookupError(f"document {doc_id} not found")
    doc.status = status
    doc.error = error
    if page_count is not None:
        doc.page_count = page_count


# ---------------------------------------------------------------- elements & chunks

def delete_doc_elements(s: Session, doc_id: uuid.UUID) -> int:
    """Idempotent reprocessing: wipe previous parse output for this doc.

    ORM-level delete so cascades (chunks, table_element, records) apply on
    SQLite too, not only where FK ON DELETE CASCADE is enforced.
    """
    elements = list(s.scalars(select(Element).where(Element.doc_id == doc_id)))
    for element in elements:
        s.delete(element)
    s.flush()
    return len(elements)


def add_element(s: Session, doc_id: uuid.UUID, page: int, bbox: list[float],
                type_: str, crop_image_path: str, confidence: float | None = None,
                needs_review: bool = False, meta: dict | None = None) -> Element:
    element = Element(doc_id=doc_id, page=page, bbox=bbox, type=type_,
                      crop_image_path=crop_image_path, confidence=confidence,
                      needs_review=needs_review, meta=meta or {})
    s.add(element)
    s.flush()
    return element


def add_chunks(s: Session, element_id: uuid.UUID,
               chunks: list[tuple[str, int]]) -> list[Chunk]:
    rows = [Chunk(element_id=element_id, text=text, token_count=tokens)
            for text, tokens in chunks]
    s.add_all(rows)
    s.flush()
    return rows


@dataclass
class ChunkContext:
    """A retrieved chunk joined with its provenance (principle #3)."""

    chunk_id: uuid.UUID
    text: str
    element_id: uuid.UUID
    page: int
    crop_image_path: str
    confidence: float | None
    needs_review: bool
    doc_id: uuid.UUID
    filename: str


def get_chunk_contexts(s: Session, chunk_ids: list[uuid.UUID]) -> list[ChunkContext]:
    if not chunk_ids:
        return []
    rows = s.execute(
        select(Chunk, Element, Document)
        .join(Element, Chunk.element_id == Element.id)
        .join(Document, Element.doc_id == Document.id)
        .where(Chunk.id.in_(chunk_ids))
    ).all()
    by_id = {
        chunk.id: ChunkContext(
            chunk_id=chunk.id, text=chunk.text, element_id=element.id,
            page=element.page, crop_image_path=element.crop_image_path,
            confidence=element.confidence, needs_review=element.needs_review,
            doc_id=document.id, filename=document.filename)
        for chunk, element, document in rows
    }
    # preserve caller's (relevance) ordering
    return [by_id[cid] for cid in chunk_ids if cid in by_id]


# ---------------------------------------------------------------- chat

def get_or_create_session(s: Session, kb_id: uuid.UUID,
                          session_id: uuid.UUID | None) -> ChatSession:
    if session_id is not None:
        existing = s.get(ChatSession, session_id)
        if existing is not None:
            return existing
    session = ChatSession(kb_id=kb_id)
    s.add(session)
    s.flush()
    return session


def add_message(s: Session, session_id: uuid.UUID, role: str, content: str,
                citations: list | None = None,
                verification: dict | None = None) -> ChatMessage:
    msg = ChatMessage(session_id=session_id, role=role, content=content,
                      citations=citations, verification=verification)
    s.add(msg)
    s.flush()
    return msg
