"""Ingestion Celery tasks (Phase 2: layout -> text/table/figure elements).

Idempotent by doc_id (SPEC Phase 1): reprocessing first deletes the doc's
previous elements (Postgres, cascading) and vectors (Qdrant), so a worker
killed mid-job and redelivered (acks_late) never produces duplicates.

Every element stores a crop image (principle #3). Tables produce the three
representations; a VLM contract failure flags needs_review and keeps the
crop + salvaged HTML — the job never crashes on a bad table (SPEC §0.3).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from tablerag.core.config import get_settings
from tablerag.core.queue import TASK_PROCESS_DOCUMENT, celery_app
from tablerag.ingestion.chunking import chunk_text
from tablerag.ingestion.extract import PdfError
from tablerag.ingestion.layout import PageLayout, analyze_document, crop_region_png
from tablerag.ingestion.ocr import ocr_page
from tablerag.ingestion.table_pipeline import parse_table_region, summarize_table
from tablerag.models.base import ModelProvider, TableCtx, Vector
from tablerag.models.registry import get_provider
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope
from tablerag.storage.object_store import get_object_store, page_image_key
from tablerag.storage.qdrant import (
    COLLECTION_CHUNKS,
    COLLECTION_RECORDS,
    COLLECTION_TABLE_SUMMARIES,
    get_vector_store,
)

logger = logging.getLogger(__name__)

EMBED_BATCH = 32


def element_image_key(kb_id, doc_id, element_id) -> str:
    return f"kbs/{kb_id}/docs/{doc_id}/elements/{element_id}.png"


async def _embed_all(embedder: ModelProvider, texts: list[str]) -> list[Vector]:
    vectors: list[Vector] = []
    for i in range(0, len(texts), EMBED_BATCH):
        vectors.extend(await embedder.embed(texts[i:i + EMBED_BATCH]))
    return vectors


def _ingest_table(s, store, kb_id, doc_id, page: int, bbox, crop_png: bytes,
                  grid, is_complex: bool, locale: str | None,
                  records_out: list, summaries_out: list) -> None:
    """Create one table element with its three representations."""
    result = asyncio.run(parse_table_region(crop_png, grid, is_complex, locale))
    element_id = uuid.uuid4()
    image_key = element_image_key(kb_id, doc_id, element_id)
    store.put(image_key, crop_png, "image/png")
    meta = {"parse_error": result.error} if result.error else {}
    repo.add_element(s, doc_id, page, bbox=list(bbox), type_="table",
                     crop_image_path=image_key, confidence=None,
                     needs_review=result.needs_review, meta=meta,
                     element_id=element_id)
    summary = asyncio.run(summarize_table(result.html)) if result.html else None
    repo.add_table_element(s, element_id, result.html or None, summary,
                           result.n_rows, result.n_cols, result.parse_strategy)
    if result.records:
        rows = repo.add_records(s, element_id, result.records)
        records_out.extend((row.id, row.text_repr, element_id) for row in rows)
    if summary:
        summaries_out.append((element_id, summary))
    if result.needs_review:
        logger.warning("doc %s page %d: table flagged needs_review (%s)",
                       doc_id, page, result.error)


def _ingest_page(s, store, settings, kb_id, doc_id, layout: PageLayout,
                 locale: str | None, chunks_out: list, records_out: list,
                 summaries_out: list) -> None:
    page_key = page_image_key(kb_id, doc_id, layout.page)
    store.put(page_key, layout.image_png, "image/png")
    full_bbox = [0.0, 0.0, layout.width, layout.height]

    def add_text_element(text: str, bbox, crop_key: str, confidence: float,
                         meta: dict) -> None:
        element = repo.add_element(s, doc_id, layout.page, bbox=bbox,
                                   type_="text", crop_image_path=crop_key,
                                   confidence=confidence, meta=meta)
        chunks = chunk_text(text, target_tokens=settings.chunk_target_tokens,
                            overlap_ratio=settings.chunk_overlap_ratio)
        rows = repo.add_chunks(s, element.id,
                               [(c.text, c.token_count) for c in chunks])
        chunks_out.extend((row.id, row.text, element.id) for row in rows)

    if layout.is_scan:
        # scanned page: everything goes down the VLM path (SPEC Phase 2 §6)
        text, tables_present = asyncio.run(ocr_page(layout.image_png))
        if text:
            add_text_element(text, full_bbox, page_key, confidence=0.85,
                             meta={"ocr": True})
        if tables_present:
            _ingest_table(s, store, kb_id, doc_id, layout.page, full_bbox,
                          layout.image_png, grid=None, is_complex=True,
                          locale=locale, records_out=records_out,
                          summaries_out=summaries_out)
        return

    for region in layout.regions:
        crop = crop_region_png(layout.image_png, layout.width, region.bbox)
        if region.type == "text":
            element_id = uuid.uuid4()
            crop_key = element_image_key(kb_id, doc_id, element_id)
            store.put(crop_key, crop, "image/png")
            element = repo.add_element(s, doc_id, layout.page,
                                       bbox=list(region.bbox), type_="text",
                                       crop_image_path=crop_key, confidence=1.0,
                                       element_id=element_id)
            chunks = chunk_text(region.text,
                                target_tokens=settings.chunk_target_tokens,
                                overlap_ratio=settings.chunk_overlap_ratio)
            rows = repo.add_chunks(s, element.id,
                                   [(c.text, c.token_count) for c in chunks])
            chunks_out.extend((row.id, row.text, element.id) for row in rows)
        elif region.type == "table":
            _ingest_table(s, store, kb_id, doc_id, layout.page, region.bbox,
                          crop, region.grid, region.complex, locale,
                          records_out, summaries_out)
        elif region.type == "figure":
            # C5: store image + caption, mark figure, never extract data
            element_id = uuid.uuid4()
            crop_key = element_image_key(kb_id, doc_id, element_id)
            store.put(crop_key, crop, "image/png")
            repo.add_element(s, doc_id, layout.page, bbox=list(region.bbox),
                             type_="figure", crop_image_path=crop_key,
                             confidence=1.0,
                             meta={"caption": region.caption} if region.caption else {},
                             element_id=element_id)


@celery_app.task(name=TASK_PROCESS_DOCUMENT, bind=True)
def process_document(self, doc_id_str: str) -> None:
    doc_id = uuid.UUID(doc_id_str)
    settings = get_settings()
    store = get_object_store()
    vector_store = get_vector_store()

    with session_scope() as s:
        doc = repo.get_document(s, doc_id)
        if doc is None:
            logger.warning("process_document: document %s no longer exists", doc_id)
            return
        kb = repo.get_kb(s, doc.kb_id)
        kb_id, file_path = doc.kb_id, doc.file_path
        # locale is declared per-KB (SPEC Phase 2 §5: prefer declared over guessed)
        locale = (kb.config or {}).get("locale") if kb else None
        repo.set_document_status(s, doc_id, "parsing")

    try:
        pdf_bytes = store.get(file_path)
        pages = analyze_document(pdf_bytes, dpi=settings.page_render_dpi,
                                 min_chars=settings.scan_min_chars_per_page)

        # --- idempotency barrier: wipe any previous output for this doc ---
        vector_store.ensure_collections()
        vector_store.delete_doc(doc_id)

        chunks_out: list[tuple[uuid.UUID, str, uuid.UUID]] = []
        records_out: list[tuple[uuid.UUID, str, uuid.UUID]] = []
        summaries_out: list[tuple[uuid.UUID, str]] = []
        with session_scope() as s:
            repo.delete_doc_elements(s, doc_id)
            for layout in pages:
                _ingest_page(s, store, settings, kb_id, doc_id, layout, locale,
                             chunks_out, records_out, summaries_out)
            repo.set_document_status(s, doc_id, "indexing", page_count=len(pages))

        embedder = get_provider("embedder")
        if chunks_out:
            vectors = asyncio.run(_embed_all(embedder, [t for _, t, _ in chunks_out]))
            vector_store.upsert(
                COLLECTION_CHUNKS,
                ids=[cid for cid, _, _ in chunks_out],
                dense=[v.dense for v in vectors],
                payloads=[{"kb_id": str(kb_id), "doc_id": str(doc_id),
                           "element_id": str(eid), "chunk_id": str(cid)}
                          for cid, _, eid in chunks_out])
        if records_out:
            vectors = asyncio.run(_embed_all(embedder, [t for _, t, _ in records_out]))
            vector_store.upsert(
                COLLECTION_RECORDS,
                ids=[rid for rid, _, _ in records_out],
                dense=[v.dense for v in vectors],
                payloads=[{"kb_id": str(kb_id), "doc_id": str(doc_id),
                           "element_id": str(eid), "record_id": str(rid)}
                          for rid, _, eid in records_out])
        if summaries_out:
            vectors = asyncio.run(_embed_all(embedder, [t for _, t in summaries_out]))
            vector_store.upsert(
                COLLECTION_TABLE_SUMMARIES,
                ids=[eid for eid, _ in summaries_out],  # 1:1 with the table element
                dense=[v.dense for v in vectors],
                payloads=[{"kb_id": str(kb_id), "doc_id": str(doc_id),
                           "element_id": str(eid)}
                          for eid, _ in summaries_out])

        with session_scope() as s:
            repo.set_document_status(s, doc_id, "done", page_count=len(pages))
        logger.info("doc %s ingested: %d pages, %d chunks, %d records, %d summaries",
                    doc_id, len(pages), len(chunks_out), len(records_out),
                    len(summaries_out))

    except Exception as e:  # noqa: BLE001 — always record a human-readable failure
        message = str(e) if isinstance(e, PdfError) else \
            f"Processing failed: {type(e).__name__}: {e}"
        logger.exception("doc %s ingestion failed", doc_id)
        with session_scope() as s:
            repo.set_document_status(s, doc_id, "failed", error=message)
        raise
