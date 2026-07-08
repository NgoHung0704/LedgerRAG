"""Repository functions — the only way either pipeline touches Postgres."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from tablerag.storage.orm import (
    AppSetting,
    ChatMessage,
    ChatSession,
    Chunk,
    Document,
    Element,
    KnowledgeBase,
    Record,
    TableElement,
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
                needs_review: bool = False, meta: dict | None = None,
                element_id: uuid.UUID | None = None) -> Element:
    element = Element(id=element_id or uuid.uuid4(), doc_id=doc_id, page=page,
                      bbox=bbox, type=type_,
                      crop_image_path=crop_image_path, confidence=confidence,
                      needs_review=needs_review, meta=meta or {})
    s.add(element)
    s.flush()
    return element


def add_table_element(s: Session, element_id: uuid.UUID, html: str | None,
                      summary: str | None, n_rows: int | None, n_cols: int | None,
                      parse_strategy: str) -> TableElement:
    table = TableElement(element_id=element_id, html=html, summary=summary,
                         n_rows=n_rows, n_cols=n_cols,
                         parse_strategy=parse_strategy)
    s.add(table)
    s.flush()
    return table


def add_records(s: Session, table_element_id: uuid.UUID,
                records: list[dict]) -> list[Record]:
    """records: [{dimensions, metrics, raw_values, text_repr}, ...]"""
    rows = [Record(table_element_id=table_element_id,
                   dimensions=r["dimensions"], metrics=r["metrics"],
                   raw_values=r["raw_values"], text_repr=r["text_repr"])
            for r in records]
    s.add_all(rows)
    s.flush()
    return rows


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


@dataclass
class TableSource:
    """A retrieved table hit hydrated with its parent-table HTML and full
    provenance (principle #3 + SPEC Phase 2 §6: record hits pull the whole
    parent table into context, never a lone record)."""

    element_id: uuid.UUID
    doc_id: uuid.UUID
    filename: str
    page: int
    html: str | None
    summary: str | None
    crop_image_path: str
    confidence: float | None
    needs_review: bool


def get_table_sources(s: Session, element_ids: list[uuid.UUID]) -> list[TableSource]:
    if not element_ids:
        return []
    rows = s.execute(
        select(TableElement, Element, Document)
        .join(Element, TableElement.element_id == Element.id)
        .join(Document, Element.doc_id == Document.id)
        .where(TableElement.element_id.in_(element_ids))
    ).all()
    by_id = {
        table.element_id: TableSource(
            element_id=table.element_id, doc_id=document.id,
            filename=document.filename, page=element.page,
            html=table.html, summary=table.summary,
            crop_image_path=element.crop_image_path,
            confidence=element.confidence, needs_review=element.needs_review)
        for table, element, document in rows
    }
    return [by_id[eid] for eid in element_ids if eid in by_id]


def get_document_view(s: Session, doc_id: uuid.UUID,
                      records_preview: int = 8) -> list[dict]:
    """Everything ingestion produced for one document, element by element —
    the inspector view (what did parsing actually output?). Tables expose all
    three representations (html / records / summary) plus provenance."""
    elements = list(s.scalars(select(Element).where(Element.doc_id == doc_id)))
    elements.sort(key=lambda e: (e.page, (e.bbox or [0, 0])[1]
                                 if isinstance(e.bbox, list) else 0))
    view = []
    for element in elements:
        chunks = list(s.scalars(
            select(Chunk).where(Chunk.element_id == element.id)))
        item: dict = {
            "id": element.id,
            "page": element.page,
            "type": element.type,
            "confidence": element.confidence,
            "needs_review": element.needs_review,
            "parse_error": (element.meta or {}).get("parse_error"),
            "caption": (element.meta or {}).get("caption"),
            "ocr": bool((element.meta or {}).get("ocr")),
            "unusable": bool((element.meta or {}).get("unusable")),
            "confidence_detail": (element.meta or {}).get("confidence_detail"),
            "chunk_count": len(chunks),
            "text_preview": chunks[0].text[:600] if chunks else None,
            "table": None,
        }
        table = s.get(TableElement, element.id)
        if table is not None:
            records = list(s.scalars(
                select(Record).where(Record.table_element_id == element.id)))
            item["table"] = {
                "html": table.html,
                "summary": table.summary,
                "n_rows": table.n_rows,
                "n_cols": table.n_cols,
                "parse_strategy": table.parse_strategy,
                "records_count": len(records),
                "records_preview": [
                    {"dimensions": r.dimensions, "metrics": r.metrics,
                     "raw_values": r.raw_values}
                    for r in records[:records_preview]
                ],
            }
        view.append(item)
    return view


def get_element_detail(s: Session, element_id: uuid.UUID) -> dict | None:
    element = s.get(Element, element_id)
    if element is None:
        return None
    document = s.get(Document, element.doc_id)
    detail = {
        "id": element.id, "doc_id": element.doc_id,
        "filename": document.filename if document else "",
        "page": element.page, "type": element.type,
        "confidence": element.confidence, "needs_review": element.needs_review,
        "meta": element.meta, "table": None,
    }
    table = s.get(TableElement, element_id)
    if table is not None:
        detail["table"] = {
            "html": table.html, "summary": table.summary,
            "n_rows": table.n_rows, "n_cols": table.n_cols,
            "parse_strategy": table.parse_strategy,
        }
    return detail


# ---------------------------------------------------------------- review flow

def approve_element(s: Session, element_id: uuid.UUID) -> Element | None:
    """Admin reviewed the parse and confirmed it: clear the flag; records
    return to normal retrieval treatment (SPEC Phase 3)."""
    element = s.get(Element, element_id)
    if element is None:
        return None
    element.needs_review = False
    element.meta = {**(element.meta or {}), "reviewed": "approved"}
    s.flush()
    return element


def mark_element_unusable(s: Session, element_id: uuid.UUID) -> Element | None:
    """Admin rejected the parse: records leave retrieval (caller also deletes
    the vectors), the crop image stays for the honest-fallback display."""
    element = s.get(Element, element_id)
    if element is None:
        return None
    element.needs_review = False
    element.meta = {**(element.meta or {}), "unusable": True,
                    "reviewed": "unusable"}
    s.flush()
    return element


# ---------------------------------------------------------------- app settings

def get_setting(s: Session, key: str) -> dict | None:
    row = s.get(AppSetting, key)
    return row.value if row else None


def set_setting(s: Session, key: str, value: dict) -> None:
    row = s.get(AppSetting, key)
    if row is None:
        s.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    s.flush()


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
