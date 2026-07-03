"""Ingestion Celery tasks.

Idempotent by doc_id (SPEC Phase 1): reprocessing first deletes the doc's
previous elements (Postgres, cascading) and vectors (Qdrant), so a worker
killed mid-job and redelivered (acks_late) never produces duplicates.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from tablerag.core.config import get_settings
from tablerag.core.queue import TASK_PROCESS_DOCUMENT, celery_app
from tablerag.ingestion.chunking import chunk_text
from tablerag.ingestion.extract import PdfError, extract_pages
from tablerag.models.base import ModelProvider, Vector
from tablerag.models.registry import get_provider
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope
from tablerag.storage.object_store import get_object_store, page_image_key
from tablerag.storage.qdrant import COLLECTION_CHUNKS, get_vector_store

logger = logging.getLogger(__name__)

EMBED_BATCH = 32


async def _embed_all(embedder: ModelProvider, texts: list[str]) -> list[Vector]:
    vectors: list[Vector] = []
    for i in range(0, len(texts), EMBED_BATCH):
        vectors.extend(await embedder.embed(texts[i:i + EMBED_BATCH]))
    return vectors


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
        kb_id, file_path = doc.kb_id, doc.file_path
        repo.set_document_status(s, doc_id, "parsing")

    try:
        pdf_bytes = store.get(file_path)
        pages = extract_pages(pdf_bytes, dpi=settings.page_render_dpi,
                              min_chars_per_page=settings.scan_min_chars_per_page)

        # --- idempotency barrier: wipe any previous output for this doc ---
        vector_store.ensure_collections()
        vector_store.delete_doc(doc_id)

        chunk_refs: list[tuple[uuid.UUID, str, uuid.UUID]] = []  # (chunk_id, text, element_id)
        with session_scope() as s:
            repo.delete_doc_elements(s, doc_id)
            for page in pages:
                image_key = page_image_key(kb_id, doc_id, page.page)
                store.put(image_key, page.image_png, "image/png")
                element = repo.add_element(
                    s, doc_id, page.page,
                    bbox=[0.0, 0.0, page.width, page.height],
                    type_="text", crop_image_path=image_key,
                    confidence=1.0, meta={"needs_ocr": page.needs_ocr})
                if page.needs_ocr:
                    logger.info("doc %s page %d flagged needs_ocr (scan heuristic); "
                                "OCR path arrives in Phase 2", doc_id, page.page)
                    continue
                chunks = chunk_text(page.text,
                                    target_tokens=settings.chunk_target_tokens,
                                    overlap_ratio=settings.chunk_overlap_ratio)
                rows = repo.add_chunks(
                    s, element.id, [(c.text, c.token_count) for c in chunks])
                chunk_refs.extend((row.id, row.text, element.id) for row in rows)
            repo.set_document_status(s, doc_id, "indexing", page_count=len(pages))

        if chunk_refs:
            embedder = get_provider("embedder")
            vectors = asyncio.run(_embed_all(embedder, [t for _, t, _ in chunk_refs]))
            vector_store.upsert(
                COLLECTION_CHUNKS,
                ids=[cid for cid, _, _ in chunk_refs],
                dense=[v.dense for v in vectors],
                payloads=[{"kb_id": str(kb_id), "doc_id": str(doc_id),
                           "element_id": str(eid), "chunk_id": str(cid)}
                          for cid, _, eid in chunk_refs])

        with session_scope() as s:
            repo.set_document_status(s, doc_id, "done", page_count=len(pages))
        logger.info("doc %s ingested: %d pages, %d chunks",
                    doc_id, len(pages), len(chunk_refs))

    except Exception as e:  # noqa: BLE001 — always record a human-readable failure
        message = str(e) if isinstance(e, PdfError) else \
            f"Processing failed: {type(e).__name__}: {e}"
        logger.exception("doc %s ingestion failed", doc_id)
        with session_scope() as s:
            repo.set_document_status(s, doc_id, "failed", error=message)
        raise
