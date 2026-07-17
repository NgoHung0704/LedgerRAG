"""Re-indexing for manual edits (SPEC §0.3 human-in-the-loop review).

When an admin corrects a parsed element in the Inspector, the change must
reach retrieval — otherwise answers keep quoting the stale parse. This module
applies the edit in Postgres and rebuilds that element's vectors from its new
state. It lives at top level (not under ingestion/ or query/) so the API can
use it without importing either pipeline — ingestion↔query isolation
(principle #1) is untouched.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from tablerag.core.config import get_settings
from tablerag.ingestion.chunking import chunk_text
from tablerag.ingestion.table_pipeline import build_text_repr
from tablerag.models.registry import get_provider
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope
from tablerag.storage.orm import Chunk, Document, Element, Record, TableElement
from tablerag.storage.qdrant import (
    COLLECTION_CHUNKS,
    COLLECTION_RECORDS,
    COLLECTION_TABLE_SUMMARIES,
    get_vector_store,
)


def _rechunk(s, element: Element, text: str) -> None:
    for chunk in list(element.chunks):
        s.delete(chunk)
    s.flush()
    settings = get_settings()
    chunks = chunk_text(text, target_tokens=settings.chunk_target_tokens,
                        overlap_ratio=settings.chunk_overlap_ratio)
    repo.add_chunks(s, element.id, [(c.text, c.token_count) for c in chunks])


def _replace_records(s, element_id: uuid.UUID, records: list[dict]) -> None:
    for rec in list(s.get(TableElement, element_id).records):
        s.delete(rec)
    s.flush()
    prepared = []
    for r in records:
        dims = r.get("dimensions", {})
        metrics = r.get("metrics", {})
        raw = r.get("raw_values", {})
        prepared.append({"dimensions": dims, "metrics": metrics,
                         "raw_values": raw,
                         "text_repr": build_text_repr(dims, metrics, raw)})
    if prepared:
        repo.add_records(s, element_id, prepared)


def apply_element_edit(element_id: uuid.UUID, *, text: str | None = None,
                       html: str | None = None, summary: str | None = None,
                       records: list[dict] | None = None) -> bool:
    """Apply the edit in Postgres (sync). Clears needs_review and marks the
    element edited. Returns False if the element does not exist."""
    with session_scope() as s:
        element = s.get(Element, element_id)
        if element is None:
            return False
        if text is not None and element.type == "text":
            _rechunk(s, element, text)
        table = s.get(TableElement, element_id)
        if table is not None:
            if html is not None:
                table.html = html or None
            if summary is not None:
                table.summary = summary or None
            if records is not None:
                _replace_records(s, element_id, records)
        element.needs_review = False
        element.meta = {**(element.meta or {}), "edited": True}
    return True


async def reindex_element(element_id: uuid.UUID) -> None:
    """Wipe and rebuild all vectors for one element from its current Postgres
    state (chunks for text, records + summary for tables)."""
    store = get_vector_store()
    store.ensure_collections()
    store.delete_element(element_id)

    jobs: list[tuple[str, object, str, dict]] = []  # (collection, id, text, payload)
    with session_scope() as s:
        element = s.get(Element, element_id)
        if element is None:
            return
        document = s.get(Document, element.doc_id)
        if document is None:
            return
        base = {"kb_id": str(document.kb_id), "doc_id": str(document.id),
                "element_id": str(element_id)}
        for chunk in s.query(Chunk).filter(Chunk.element_id == element_id):
            jobs.append((COLLECTION_CHUNKS, chunk.id, chunk.text,
                         {**base, "chunk_id": str(chunk.id)}))
        table = s.get(TableElement, element_id)
        if table is not None:
            if table.summary:
                jobs.append((COLLECTION_TABLE_SUMMARIES, element_id,
                             table.summary, dict(base)))
            for rec in s.query(Record).filter(
                    Record.table_element_id == element_id):
                jobs.append((COLLECTION_RECORDS, rec.id, rec.text_repr,
                             {**base, "record_id": str(rec.id)}))

    if not jobs:
        return
    embedder = get_provider("embedder")
    vectors = await embedder.embed([job[2] for job in jobs])
    grouped: dict[str, tuple[list, list, list, list]] = defaultdict(
        lambda: ([], [], [], []))
    for (collection, id_, text, payload), vector in zip(jobs, vectors):
        ids, dense, payloads, texts = grouped[collection]
        ids.append(id_)
        dense.append(vector.dense)
        payloads.append(payload)
        texts.append(text)
    for collection, (ids, dense, payloads, texts) in grouped.items():
        store.upsert(collection, ids, dense, payloads, texts=texts)
