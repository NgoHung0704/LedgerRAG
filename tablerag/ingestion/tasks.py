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


def _box_to_bbox(box: tuple[float, float, float, float], layout) -> list[float]:
    """Fractional region box -> PDF-point bbox for provenance."""
    x0, y0, x1, y1 = box
    return [x0 * layout.width, y0 * layout.height,
            x1 * layout.width, y1 * layout.height]


async def _embed_all(embedder: ModelProvider, texts: list[str]) -> list[Vector]:
    vectors: list[Vector] = []
    for i in range(0, len(texts), EMBED_BATCH):
        vectors.extend(await embedder.embed(texts[i:i + EMBED_BATCH]))
    return vectors


def html_is_trustworthy(html: str | None, from_grid: bool,
                        error: str | None) -> bool:
    """Whether a table's HTML is faithful enough to summarize (and thus to
    index by summary rather than a raw cell dump).

    A text-layer table (`from_grid`) has geometry-derived HTML that is correct
    even when the VLM failed to structure it into records and the table was
    flagged — the Glossaire illustrative table (clean HTML, multi-level header,
    0 records, needs_review). Only a SCAN's salvaged HTML after a parse error
    would summarize to junk. Measured need: without a summary such a table is
    indexed by raw cells, which a reranker ranks below clean prose, so it falls
    out of context and its questions get refused (LOW CONFIDENCE still blocks
    asserting numbers from it — honest-failure contract intact)."""
    return bool(html) and (from_grid or not error)


def _ingest_table(s, store, kb_id, doc_id, page: int, bbox, crop_png: bytes,
                  grid, is_complex: bool, locale: str | None,
                  records_out: list, summaries_out: list,
                  double_read: bool = True,
                  extra_meta: dict | None = None) -> None:
    """Create one table element with its three representations + confidence."""
    from tablerag.core.config import get_settings
    from tablerag.ingestion.confidence import assess

    settings = get_settings()
    result = asyncio.run(parse_table_region(crop_png, grid, is_complex, locale))

    # --- Phase 3 confidence: structural + double-read + arithmetic ---
    confidence: float | None = None
    needs_review = result.needs_review
    confidence_detail: dict | None = None
    if result.records:
        second_records = None
        if (double_read and result.parse_strategy == "vlm"
                and not result.needs_review):
            # second independent read. Cross-model when configured (a different
            # architecture doesn't share qwen's blind spots on merged cells);
            # otherwise same-model seed-shift (catches only random divergence).
            from tablerag.models.registry import get_double_read_provider

            verifier = get_double_read_provider()
            # keep the grid available on the 2nd read too (same text-layer hint,
            # is_complex=True still forces the VLM path)
            second = asyncio.run(
                parse_table_region(crop_png, grid, True, locale,
                                   provider=verifier)
                if verifier is not None else
                parse_table_region(crop_png, grid, True, locale, read_variant=1))
            if not second.error and second.records:
                second_records = second.records
        report = assess(
            result.html, result.records, second_records,
            review_threshold=settings.confidence_review_threshold,
            agreement_threshold=settings.double_read_agreement_threshold)
        confidence = report.confidence
        needs_review = needs_review or report.needs_review
        confidence_detail = report.detail

    element_id = uuid.uuid4()
    image_key = element_image_key(kb_id, doc_id, element_id)
    store.put(image_key, crop_png, "image/png")
    meta: dict = dict(extra_meta or {})
    if result.error:
        meta["parse_error"] = result.error
    if confidence_detail:
        meta["confidence_detail"] = confidence_detail
    repo.add_element(s, doc_id, page, bbox=list(bbox), type_="table",
                     crop_image_path=image_key, confidence=confidence,
                     needs_review=needs_review, meta=meta,
                     element_id=element_id)
    summary = None
    if html_is_trustworthy(result.html, grid is not None, result.error):
        summary = asyncio.run(summarize_table(result.html, locale))
    repo.add_table_element(s, element_id, result.html or None, summary,
                           result.n_rows, result.n_cols, result.parse_strategy)
    if result.records:
        rows = repo.add_records(s, element_id, result.records)
        records_out.extend((row.id, row.text_repr, element_id) for row in rows)
    if summary:
        summaries_out.append((element_id, summary))
    elif result.html:
        from tablerag.ingestion.html_tables import html_to_text

        cell_text = html_to_text(result.html)[:2000]
        if cell_text:
            summaries_out.append((element_id, cell_text))
    if needs_review:
        logger.warning("doc %s page %d: table flagged needs_review "
                       "(error=%s, confidence=%s)",
                       doc_id, page, result.error, confidence)


def _ingest_page(s, store, settings, kb_id, doc_id, layout: PageLayout,
                 locale: str | None, chunks_out: list, records_out: list,
                 summaries_out: list, double_read: bool = True) -> None:
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
        # scanned page: no text layer, so find_tables sees nothing — the VLM
        # does OCR AND detects the table regions (SPEC Phase 2 §1 fallback),
        # then each region is parsed on its own crop. Light upscale first.
        from tablerag.ingestion.imaging import crop_fraction, ensure_min_width
        from tablerag.ingestion.region_detect import detect_table_regions

        vlm_page = ensure_min_width(layout.image_png,
                                    settings.vlm_min_image_width)
        text, tables_present = asyncio.run(ocr_page(vlm_page))
        if text:
            add_text_element(text, full_bbox, page_key, confidence=0.85,
                             meta={"ocr": True})
        if tables_present:
            regions = asyncio.run(detect_table_regions(vlm_page))
            logger.info("scan page %d: %d table region(s) detected%s",
                        layout.page, len(regions),
                        "" if regions else " — falling back to whole page")
            targets = ([(crop_fraction(vlm_page, box), _box_to_bbox(box, layout))
                        for box in regions]
                       if regions else [(vlm_page, full_bbox)])
            for crop, bbox in targets:
                _ingest_table(s, store, kb_id, doc_id, layout.page, bbox,
                              crop, grid=None, is_complex=True, locale=locale,
                              records_out=records_out,
                              summaries_out=summaries_out,
                              double_read=double_read)
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
            # prefer the high-DPI re-render from the PDF over the page crop
            table_crop = region.crop_png or crop
            extra = ({"span_pages": [layout.page] + region.span_pages}
                     if region.span_pages else None)
            _ingest_table(s, store, kb_id, doc_id, layout.page, region.bbox,
                          table_crop, region.grid, region.complex, locale,
                          records_out, summaries_out, double_read=double_read,
                          extra_meta=extra)
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
        kb_config = (kb.config or {}) if kb else {}
        locale = kb_config.get("locale")
        # double-read is toggleable per-KB (SPEC Phase 3), global default from env
        double_read = bool(kb_config.get("double_read",
                                         settings.double_read_enabled))
        repo.set_document_status(s, doc_id, "parsing")

    try:
        pdf_bytes = store.get(file_path)
        pages = analyze_document(pdf_bytes, dpi=settings.page_render_dpi,
                                 min_chars=settings.scan_min_chars_per_page,
                                 table_dpi=settings.table_crop_dpi)

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
                             chunks_out, records_out, summaries_out,
                             double_read=double_read)
            repo.set_document_status(s, doc_id, "indexing", page_count=len(pages))

        embedder = get_provider("embedder")
        if chunks_out:
            texts = [t for _, t, _ in chunks_out]
            vectors = asyncio.run(_embed_all(embedder, texts))
            vector_store.upsert(
                COLLECTION_CHUNKS,
                ids=[cid for cid, _, _ in chunks_out],
                dense=[v.dense for v in vectors],
                payloads=[{"kb_id": str(kb_id), "doc_id": str(doc_id),
                           "element_id": str(eid), "chunk_id": str(cid)}
                          for cid, _, eid in chunks_out],
                texts=texts)
        if records_out:
            texts = [t for _, t, _ in records_out]
            vectors = asyncio.run(_embed_all(embedder, texts))
            vector_store.upsert(
                COLLECTION_RECORDS,
                ids=[rid for rid, _, _ in records_out],
                dense=[v.dense for v in vectors],
                payloads=[{"kb_id": str(kb_id), "doc_id": str(doc_id),
                           "element_id": str(eid), "record_id": str(rid)}
                          for rid, _, eid in records_out],
                texts=texts)
        if summaries_out:
            texts = [t for _, t in summaries_out]
            vectors = asyncio.run(_embed_all(embedder, texts))
            vector_store.upsert(
                COLLECTION_TABLE_SUMMARIES,
                ids=[eid for eid, _ in summaries_out],  # 1:1 with the table element
                dense=[v.dense for v in vectors],
                payloads=[{"kb_id": str(kb_id), "doc_id": str(doc_id),
                           "element_id": str(eid)}
                          for eid, _ in summaries_out],
                texts=texts)

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
