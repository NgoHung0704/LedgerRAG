"""Repository functions — the only way either pipeline touches Postgres."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from tablerag.query.neighbours import NeighbourCandidate

from tablerag.storage.orm import (
    AppSetting,
    Assistant,
    AssistantConversation,
    AssistantKB,
    AuditEvent,
    ChatMessage,
    ChatSession,
    Chunk,
    Document,
    Element,
    KnowledgeBase,
    MessageFeedback,
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


def get_or_create_kb_by_name(s: Session, name: str,
                             config: dict | None = None) -> KnowledgeBase:
    """Match a KB by name (case-insensitive, oldest wins) or create it. Powers
    the consume folder, where a subfolder name maps to a KB. Names are not
    unique in the schema, so an existing match is reused rather than duplicated."""
    existing = s.scalars(
        select(KnowledgeBase)
        .where(func.lower(KnowledgeBase.name) == name.lower())
        .order_by(KnowledgeBase.created_at)).first()
    if existing is not None:
        return existing
    return create_kb(s, name=name, config=config)


def kb_document_status_counts(s: Session) -> dict[uuid.UUID, dict[str, int]]:
    """Per-KB document counts grouped by status, in a single query — powers the
    at-a-glance processing/failed indicator on the KB list without an N+1 scan
    (one aggregate for all KBs, not one query per card)."""
    rows = s.execute(
        select(Document.kb_id, Document.status, func.count())
        .group_by(Document.kb_id, Document.status)
    ).all()
    counts: dict[uuid.UUID, dict[str, int]] = {}
    for kb_id, status, count in rows:
        counts.setdefault(kb_id, {})[status] = count
    return counts


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


def needs_review_elements(s: Session, kb_id: uuid.UUID) -> list[dict]:
    """Flagged, still-usable elements across a KB, newest doc first — the
    review queue (SPEC Phase 5: pull needs_review out of per-document admin
    into a natural flow). Excludes elements already marked unusable."""
    rows = s.execute(
        select(Element, Document.filename)
        .join(Document, Element.doc_id == Document.id)
        .where(Document.kb_id == kb_id, Element.needs_review.is_(True))
        .order_by(Document.created_at.desc(), Element.page.asc())
    ).all()
    out = []
    for element, filename in rows:
        if (element.meta or {}).get("unusable"):
            continue
        out.append({"element_id": element.id, "doc_id": element.doc_id,
                    "filename": filename, "page": element.page,
                    "type": element.type, "confidence": element.confidence})
    return out


def content_sample(s: Session, kb_id: uuid.UUID, *, max_docs: int = 5,
                   max_chars: int = 4000) -> str:
    """A short, representative sample of a KB's content for auto-describing it
    (SPEC Phase 5: a good description is what the router reads). Filenames plus
    the opening text of the first documents and any table summaries — enough
    for an LLM to say what subjects the KB covers, cheap to assemble."""
    docs = list(s.scalars(
        select(Document).where(Document.kb_id == kb_id)
        .order_by(Document.created_at.asc()).limit(max_docs)))
    parts: list[str] = []
    for doc in docs:
        parts.append(f"# {doc.filename}")
        chunk = s.scalars(
            select(Chunk).join(Element, Chunk.element_id == Element.id)
            .where(Element.doc_id == doc.id).limit(1)).first()
        if chunk and chunk.text:
            parts.append(chunk.text[:600])
        for summary in s.scalars(
                select(TableElement.summary).join(
                    Element, TableElement.element_id == Element.id)
                .where(Element.doc_id == doc.id,
                       TableElement.summary.is_not(None)).limit(2)):
            if summary:
                parts.append(f"[table] {summary}")
    return "\n".join(parts)[:max_chars].strip()


def delete_kb(s: Session, kb_id: uuid.UUID) -> bool:
    """Delete a KB row. Postgres FK cascade removes its documents (→ elements,
    chunks, records, tables) and chat sessions (→ messages, feedback). The
    caller must purge Qdrant vectors and object-store files first (those are
    not in the DB). Audit events keep their kb_id (no FK) so the trail survives."""
    kb = get_kb(s, kb_id)
    if kb is None:
        return False
    s.delete(kb)
    s.flush()
    return True


def delete_document(s: Session, doc_id: uuid.UUID) -> uuid.UUID | None:
    """Delete a document and everything it owns in Postgres (elements, chunks,
    table_element, records cascade). Returns its kb_id so the caller can also
    drop vectors and object-store files. Returns None if it never existed."""
    doc = s.get(Document, doc_id)
    if doc is None:
        return None
    kb_id = doc.kb_id
    s.delete(doc)
    s.flush()
    return kb_id


def delete_documents(s: Session, doc_ids: list[uuid.UUID]) -> int:
    """Bulk-delete document rows in one transaction (elements, chunks,
    table_element, records cascade). ORM-level delete so cascades apply on
    SQLite too. Returns how many rows existed and were removed."""
    if not doc_ids:
        return 0
    docs = list(s.scalars(select(Document).where(Document.id.in_(doc_ids))))
    for doc in docs:
        s.delete(doc)
    s.flush()
    return len(docs)


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
    element_type: str = "text"  # 'figure' -> the text is a description
    # the heading above this element, when ingestion recorded one — see
    # overlap.period_of, which needs it to tell two look-alike sources apart
    context: str = ""


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
            doc_id=document.id, filename=document.filename,
            element_type=element.type,
            context=(element.meta or {}).get("context", ""))
        for chunk, element, document in rows
    }
    # preserve caller's (relevance) ordering
    return [by_id[cid] for cid in chunk_ids if cid in by_id]


def get_page_elements(s: Session, doc_ids: list[uuid.UUID]
                      ) -> list["NeighbourCandidate"]:
    """Every element of these documents, as neighbour candidates.

    Whole documents rather than a page window: reading order is only correct
    when nothing is missing from it, and a document's element rows are small."""
    from tablerag.query.neighbours import NeighbourCandidate

    if not doc_ids:
        return []
    rows = s.query(Element).filter(Element.doc_id.in_(doc_ids)).all()
    return [NeighbourCandidate(
        element_id=row.id, doc_id=row.doc_id, page=row.page,
        y=float((row.bbox or [0, 0, 0, 0])[1]),
        x=float((row.bbox or [0, 0, 0, 0])[0]), type=row.type)
        for row in rows]


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
    # the heading above this table, when ingestion recorded one — see
    # overlap.period_of, which needs it to tell two look-alike sources apart
    context: str = ""


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
            confidence=element.confidence, needs_review=element.needs_review,
            context=(element.meta or {}).get("context", ""))
        for table, element, document in rows
    }
    return [by_id[eid] for eid in element_ids if eid in by_id]


def get_record_texts(s: Session,
                     record_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """`text_repr` of specific records, keyed by id.

    Retrieval knows WHICH rows matched, but a record hit is expanded to the
    whole parent table for context (SPEC Phase 2 §6). Keeping the matched rows
    lets the answer step point at the needle as well as the haystack."""
    if not record_ids:
        return {}
    return {r.id: r.text_repr for r in
            s.scalars(select(Record).where(Record.id.in_(record_ids)))}


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
            # what the VLM saw in the picture, and whether it judged the
            # picture to carry any information at all
            "description": (element.meta or {}).get("description"),
            "decorative": (element.meta or {}).get("figure_kind") == "decorative",
            # why a chart was trusted or flagged: its drawn bars vs the values
            # the model says it read off them
            "chart_check": (element.meta or {}).get("chart_check"),
            "ocr": bool((element.meta or {}).get("ocr")),
            "layout_suspect": bool((element.meta or {}).get("layout_suspect")),
            "unusable": bool((element.meta or {}).get("unusable")),
            "edited": bool((element.meta or {}).get("edited")),
            # how many edits can still be taken back
            "undo_steps": revision_count(s, element.id),
            "confidence_detail": (element.meta or {}).get("confidence_detail"),
            "span_pages": (element.meta or {}).get("span_pages"),
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


MAX_REVISIONS = 10


def snapshot_element(s: Session, element_id: uuid.UUID, action: str) -> None:
    """Record what this element holds NOW, before something replaces it.

    Called on the way in to every edit, so undo restores the state the reviewer
    was looking at when they pressed save. Trimmed to the last few: the point
    is to take back a mistake, not to archive a document's life.

    Reprocessing already undoes anything — but it re-runs the whole document
    and discards every other correction made to it, which is far too blunt
    when what you want back is the previous save of one element."""
    from tablerag.storage.orm import ElementRevision

    element = s.get(Element, element_id)
    if element is None:
        return
    table = s.get(TableElement, element_id)
    s.add(ElementRevision(
        element_id=element_id, action=action,
        text="\n\n".join(c.text for c in element.chunks) or None,
        html=table.html if table else None,
        summary=table.summary if table else None,
        records=[{"dimensions": r.dimensions, "metrics": r.metrics,
                  "raw_values": r.raw_values} for r in table.records]
        if table else None,
        element_type=element.type, needs_review=element.needs_review))
    s.flush()

    keep = list(s.scalars(
        select(ElementRevision)
        .where(ElementRevision.element_id == element_id)
        .order_by(ElementRevision.created_at.desc(), ElementRevision.id.desc())))
    for revision in keep[MAX_REVISIONS:]:
        s.delete(revision)


def split_children(s: Session, element_id: uuid.UUID) -> list[uuid.UUID]:
    """Elements carved off this one by a split, so undoing it can take them
    back too. Matched on meta rather than a column: create_all adds tables,
    never columns, and this needs no schema change on a live database."""
    rows = s.scalars(select(Element).where(Element.doc_id == select(
        Element.doc_id).where(Element.id == element_id).scalar_subquery()))
    return [e.id for e in rows
            if (e.meta or {}).get("split_from") == str(element_id)]


def revision_count(s: Session, element_id: uuid.UUID) -> int:
    from tablerag.storage.orm import ElementRevision

    return len(list(s.scalars(
        select(ElementRevision.id)
        .where(ElementRevision.element_id == element_id))))


def pop_revision(s: Session, element_id: uuid.UUID) -> dict | None:
    """The most recent snapshot, taken off the stack. None when there is none."""
    from tablerag.storage.orm import ElementRevision

    revision = s.scalars(
        select(ElementRevision)
        .where(ElementRevision.element_id == element_id)
        .order_by(ElementRevision.created_at.desc(), ElementRevision.id.desc())
        .limit(1)).first()
    if revision is None:
        return None
    data = {"action": revision.action, "text": revision.text,
            "html": revision.html, "summary": revision.summary,
            "records": revision.records, "element_type": revision.element_type,
            "needs_review": revision.needs_review}
    s.delete(revision)
    s.flush()
    return data


def document_export(s: Session, doc_id: uuid.UUID) -> tuple[dict, list[dict]] | None:
    """Everything stored for one document, in FULL — no previews.

    get_document_view truncates on purpose (600 characters of text, eight
    records) because it feeds a screen. This feeds an export whose whole point
    is that nothing is left out."""
    document = s.get(Document, doc_id)
    if document is None:
        return None
    elements = list(s.scalars(select(Element).where(Element.doc_id == doc_id)))
    elements.sort(key=lambda e: (e.page, (e.bbox or [0, 0])[1]
                                 if isinstance(e.bbox, list) else 0))
    out = []
    for element in elements:
        meta = element.meta or {}
        item = {
            "page": element.page, "type": element.type,
            "bbox": element.bbox, "confidence": element.confidence,
            "needs_review": element.needs_review,
            "context": meta.get("context") or meta.get("heading"),
            "caption": meta.get("caption"),
            "description": meta.get("description"),
            "palette": meta.get("palette"),
            "chart_check": meta.get("chart_check"),
            "parse_error": meta.get("parse_error"),
            "span_pages": meta.get("span_pages"),
            "unusable": bool(meta.get("unusable")),
            "edited": bool(meta.get("edited")),
            "ocr": bool(meta.get("ocr")),
            "layout_suspect": bool(meta.get("layout_suspect")),
            "decorative": meta.get("figure_kind") in ("decorative", "duplicate"),
            "chunks": [c.text for c in s.scalars(
                select(Chunk).where(Chunk.element_id == element.id))],
            "table": None,
        }
        table = s.get(TableElement, element.id)
        if table is not None:
            item["table"] = {
                "html": table.html, "summary": table.summary,
                "n_rows": table.n_rows, "n_cols": table.n_cols,
                "parse_strategy": table.parse_strategy,
                "records": [{"dimensions": r.dimensions, "metrics": r.metrics,
                             "raw_values": r.raw_values}
                            for r in table.records],
            }
        out.append(item)
    return ({"filename": document.filename, "status": document.status,
             "page_count": document.page_count, "error": document.error}, out)


def delete_elements(s: Session, element_ids: list[uuid.UUID]) -> list[str]:
    """Drop parsed elements and everything they own (chunks, table, records
    cascade). Returns their crop-image keys so the caller can clear those too.

    Destructive but not final: the original file is untouched, so reprocessing
    the document brings the page back exactly as ingestion produced it."""
    if not element_ids:
        return []
    rows = list(s.scalars(select(Element).where(Element.id.in_(element_ids))))
    crops = [e.crop_image_path for e in rows if e.crop_image_path]
    for element in rows:
        s.delete(element)
    s.flush()
    return crops


def page_element_ids(s: Session, doc_id: uuid.UUID,
                     page: int) -> list[uuid.UUID]:
    return list(s.scalars(
        select(Element.id).where(Element.doc_id == doc_id,
                                 Element.page == page)))


def get_text_elements(s: Session, doc_id: uuid.UUID) -> list[dict]:
    """Text elements with position + joined text, for boilerplate detection.
    Type='text' only — running headers/footers are the target; table numbers
    must never be touched. Already-unusable elements are skipped."""
    rows = list(s.scalars(
        select(Element).where(Element.doc_id == doc_id,
                              Element.type == "text")))
    out = []
    for el in rows:
        if (el.meta or {}).get("unusable"):
            continue
        chunks = list(s.scalars(select(Chunk).where(Chunk.element_id == el.id)))
        out.append({"id": el.id, "page": el.page, "bbox": el.bbox,
                    "text": " ".join(c.text for c in chunks)})
    return out


def get_element_detail(s: Session, element_id: uuid.UUID) -> dict | None:
    element = s.get(Element, element_id)
    if element is None:
        return None
    document = s.get(Document, element.doc_id)
    chunks = list(s.scalars(select(Chunk).where(Chunk.element_id == element_id)))
    detail = {
        "id": element.id, "doc_id": element.doc_id,
        "filename": document.filename if document else "",
        "page": element.page, "type": element.type,
        "confidence": element.confidence, "needs_review": element.needs_review,
        "edited": bool((element.meta or {}).get("edited")),
        "meta": element.meta,
        "text": "\n\n".join(c.text for c in chunks) if chunks else None,
        "table": None,
    }
    table = s.get(TableElement, element_id)
    if table is not None:
        records = list(s.scalars(
            select(Record).where(Record.table_element_id == element_id)))
        detail["table"] = {
            "html": table.html, "summary": table.summary,
            "n_rows": table.n_rows, "n_cols": table.n_cols,
            "parse_strategy": table.parse_strategy,
            "records": [{"dimensions": r.dimensions, "metrics": r.metrics,
                         "raw_values": r.raw_values} for r in records],
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

# global chat guidance appended to every system prompt (admin-set); value is
# {"text": ...}. Per-KB guidance lives in kb.config["instructions"].
CHAT_INSTRUCTIONS_SETTING = "chat_instructions"


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


def log_audit(s: Session, actor: str, action: str, *,
              kb_id: uuid.UUID | None = None, doc_id: uuid.UUID | None = None,
              detail: dict | None = None) -> None:
    """Record a GDPR-relevant action. Best-effort: never let audit failure
    break the operation being audited (callers wrap it)."""
    s.add(AuditEvent(actor=actor, action=action, kb_id=kb_id, doc_id=doc_id,
                     detail=detail))
    s.flush()


def recent_audit(s: Session, limit: int = 200) -> list[AuditEvent]:
    return list(s.scalars(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)))


def set_feedback(s: Session, message_id: uuid.UUID, value: int) -> int | None:
    """Upsert 👍/👎 on a message. value 0 clears it; returns the stored value
    (or None when cleared). One row per message (unique constraint)."""
    row = s.scalars(
        select(MessageFeedback).where(MessageFeedback.message_id == message_id)
    ).first()
    if value == 0:
        if row is not None:
            s.delete(row)
        return None
    if row is None:
        s.add(MessageFeedback(message_id=message_id, value=value))
    else:
        row.value = value
    s.flush()
    return value


def add_message(s: Session, session_id: uuid.UUID, role: str, content: str,
                citations: list | None = None,
                verification: dict | None = None) -> ChatMessage:
    msg = ChatMessage(session_id=session_id, role=role, content=content,
                      citations=citations, verification=verification)
    s.add(msg)
    s.flush()
    return msg


def get_recent_messages(s: Session, session_id: uuid.UUID,
                        limit: int = 6) -> list[tuple[str, str]]:
    """The last `limit` turns of a session, oldest→newest, as (role, content).

    Powers multi-turn: the query pipeline reads the thread to turn a follow-up
    ("et pour la classe II ?") into a standalone search query and to let the
    answer resolve what the user meant. Facts still come only from freshly
    retrieved sources — history is context for understanding, never a source."""
    rows = list(s.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)))
    return [(m.role, m.content) for m in reversed(rows)]


def get_session_messages(s: Session, session_id: uuid.UUID) -> list[dict]:
    """A whole thread, oldest→newest, with everything the UI needs to re-render
    it exactly as it streamed: citations, verification and any 👍/👎."""
    rows = list(s.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at, ChatMessage.id)))
    feedback = {
        f.message_id: f.value for f in s.scalars(
            select(MessageFeedback).where(
                MessageFeedback.message_id.in_([m.id for m in rows] or [None])))
    }
    return [{"id": m.id, "role": m.role, "content": m.content,
             "citations": m.citations or [], "verification": m.verification,
             "feedback": feedback.get(m.id, 0)} for m in rows]


# ---------------------------------------------------------------- assistants

def create_assistant(s: Session, name: str, description: str = "",
                     instructions: str = "", config: dict | None = None,
                     kb_ids: list[uuid.UUID] | None = None) -> Assistant:
    assistant = Assistant(name=name, description=description,
                          instructions=instructions, config=config or {})
    s.add(assistant)
    s.flush()
    set_assistant_kbs(s, assistant.id, kb_ids or [])
    return assistant


def get_assistant(s: Session, assistant_id: uuid.UUID) -> Assistant | None:
    return s.get(Assistant, assistant_id)


def list_assistants(s: Session) -> list[Assistant]:
    return list(s.scalars(select(Assistant).order_by(Assistant.created_at)))


def assistant_kb_ids(s: Session, assistant_id: uuid.UUID) -> list[uuid.UUID]:
    """The knowledge bases this assistant searches. Rows whose KB was deleted
    are gone by cascade, so this is always a live set."""
    return list(s.scalars(
        select(AssistantKB.kb_id)
        .where(AssistantKB.assistant_id == assistant_id)))


def set_assistant_kbs(s: Session, assistant_id: uuid.UUID,
                      kb_ids: list[uuid.UUID]) -> None:
    """Replace the attached set (the PATCH semantics the UI needs). Unknown KB
    ids are dropped rather than raising: a KB deleted meanwhile is not an error."""
    wanted = {k for k in kb_ids
              if s.get(KnowledgeBase, k) is not None}
    current = set(assistant_kb_ids(s, assistant_id))
    for kb_id in current - wanted:
        row = s.get(AssistantKB, {"assistant_id": assistant_id, "kb_id": kb_id})
        if row is not None:
            s.delete(row)
    for kb_id in wanted - current:
        s.add(AssistantKB(assistant_id=assistant_id, kb_id=kb_id))
    s.flush()


def delete_assistant(s: Session, assistant_id: uuid.UUID) -> bool:
    assistant = s.get(Assistant, assistant_id)
    if assistant is None:
        return False
    # the sessions themselves are not cascaded by the link table, so drop them
    # explicitly — otherwise their messages would outlive the assistant
    for link in s.scalars(select(AssistantConversation).where(
            AssistantConversation.assistant_id == assistant_id)):
        session = s.get(ChatSession, link.session_id)
        if session is not None:
            s.delete(session)  # cascades to messages (and to the link row)
    s.delete(assistant)
    s.flush()
    return True


# ------------------------------------------------------------- conversations

def link_conversation(s: Session, assistant_id: uuid.UUID,
                      session_id: uuid.UUID, title: str) -> AssistantConversation:
    """Give a session an owner and a title on its first turn; later turns just
    bump updated_at so the list stays ordered by recent activity."""
    link = s.get(AssistantConversation, session_id)
    if link is None:
        link = AssistantConversation(session_id=session_id,
                                     assistant_id=assistant_id,
                                     title=title[:120])
        s.add(link)
    else:
        link.updated_at = func.now()
    s.flush()
    return link


def list_conversations(s: Session, assistant_id: uuid.UUID,
                       limit: int = 100) -> list[dict]:
    rows = list(s.scalars(
        select(AssistantConversation)
        .where(AssistantConversation.assistant_id == assistant_id)
        .order_by(AssistantConversation.updated_at.desc())
        .limit(limit)))
    return [{"session_id": r.session_id, "title": r.title,
             "created_at": r.created_at, "updated_at": r.updated_at}
            for r in rows]


def get_conversation(s: Session, session_id: uuid.UUID
                     ) -> AssistantConversation | None:
    return s.get(AssistantConversation, session_id)


def rename_conversation(s: Session, session_id: uuid.UUID,
                        title: str) -> AssistantConversation | None:
    link = s.get(AssistantConversation, session_id)
    if link is None:
        return None
    link.title = title[:120]
    s.flush()
    return link


def delete_conversation(s: Session, session_id: uuid.UUID) -> bool:
    """Delete the thread itself — the session cascades to its messages, and to
    the link row."""
    session = s.get(ChatSession, session_id)
    if session is None:
        return False
    s.delete(session)
    s.flush()
    return True
