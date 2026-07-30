"""Re-indexing for manual edits (SPEC §0.3 human-in-the-loop review).

When an admin corrects a parsed element in the Inspector, the change must
reach retrieval — otherwise answers keep quoting the stale parse. This module
applies the edit in Postgres and rebuilds that element's vectors from its new
state. It lives at top level (not under ingestion/ or query/) so the API can
use it without importing either pipeline — ingestion↔query isolation
(principle #1) is untouched.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict

from tablerag.core.config import get_settings
from tablerag.core.table_text import html_to_text
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

logger = logging.getLogger(__name__)


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


def convert_table_to_text(element_id: uuid.UUID) -> bool:
    """Demote a wrongly detected table to a plain text element.

    Table detection sometimes fires on prose laid out in columns. Kept as a
    table, that content is indexed as records and a grid it never had; as text
    it is chunked and retrieved normally. The cells' own words become the text
    (they ARE the page's words), so nothing is invented — and the crop image
    stays, so provenance is untouched. Reversible by reprocessing the document,
    which re-runs detection from scratch.

    Returns False if the element does not exist or is not a table."""
    with session_scope() as s:
        element = s.get(Element, element_id)
        if element is None or element.type != "table":
            return False
        table = s.get(TableElement, element_id)
        text = ""
        if table is not None:
            text = html_to_text(table.html) or (table.summary or "")
            # its records go with it (relationship cascades delete-orphan)
            s.delete(table)
            s.flush()
        element.type = "text"
        element.needs_review = False
        element.meta = {**(element.meta or {}), "edited": True,
                        "converted_from": "table"}
        # empty is allowed: an image-only table leaves a text element with no
        # content, which the reviewer can fill via "re-read with the VLM"
        _rechunk(s, element, text)
    return True


def _table_region_inputs(element_id: uuid.UUID) -> dict | None:
    """Everything needed to re-render and re-read one table region: the source
    PDF, the page, the element's bbox and the KB's declared locale."""
    from tablerag.ingestion.convert import needs_conversion
    from tablerag.storage.object_store import (
        doc_converted_pdf_key,
        get_object_store,
    )
    from tablerag.storage.orm import KnowledgeBase

    with session_scope() as s:
        element = s.get(Element, element_id)
        if element is None or element.type != "table":
            return None
        document = s.get(Document, element.doc_id)
        if document is None:
            return None
        kb = s.get(KnowledgeBase, document.kb_id)
        meta = element.meta or {}
        info = {"page": element.page, "bbox": list(element.bbox or []),
                "locale": (kb.config or {}).get("locale") if kb else None,
                "kb_id": document.kb_id, "doc_id": document.id,
                "key": document.file_path, "filename": document.filename,
                # a cross-page table's stored crop is a STITCHED image of its
                # fragments; re-rendering one page would hand over half a table
                "spans_pages": len(meta.get("span_pages") or []) > 1,
                "crop_key": element.crop_image_path}
    store = get_object_store()
    if info["spans_pages"]:
        if not store.exists(info["crop_key"]):
            return None
        info["crop"] = store.get(info["crop_key"])
        return info
    # an Office document was ingested through its cached PDF rendering
    if needs_conversion(info["filename"]):
        info["key"] = doc_converted_pdf_key(info["kb_id"], info["doc_id"])
    if not store.exists(info["key"]):
        return None
    info["pdf"] = store.get(info["key"])
    return info


def _render_region(pdf_bytes: bytes, page_no: int, bbox: list[float],
                   dpi: int) -> tuple[bytes, list[list[str | None]] | None]:
    """Re-render a table's region straight from the PDF at `dpi`, and recover
    the text-layer grid under it when there is one.

    Both matter: more pixels give the VLM a better look than the crop stored at
    ingest, and the grid is the hint that made merged-cell reading work (values
    from the text layer, structure from the image)."""
    import fitz

    from tablerag.ingestion.layout import detect_tables

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc[page_no - 1]
        clip = fitz.Rect(*bbox) if len(bbox) == 4 else page.rect
        png = page.get_pixmap(dpi=dpi, clip=clip).tobytes("png")
        grid = None
        best = 0.0
        for table, candidate in detect_tables(page):
            rect = fitz.Rect(table.bbox) & clip
            if not rect.is_empty:
                area = rect.get_area()
                if area > best:
                    best, grid = area, candidate
    return png, grid


async def recheck_table(element_id: uuid.UUID) -> dict | None:
    """Parse one table again, harder — a PROPOSAL, nothing is written.

    Three things the ingest pass did not necessarily do: the region is
    re-rendered from the PDF at double the configured DPI, the text-layer grid
    is recovered as a hint, and the table is read TWICE (by a different model
    when one is configured, else the same model at a shifted seed) so the two
    reads can be scored against each other. The agreement is reported with the
    result, so the reviewer knows how much to trust it before saving.

    Returns None if the element is not a table or its source is unavailable."""
    from tablerag.ingestion.confidence import assess
    from tablerag.ingestion.imaging import ensure_min_width
    from tablerag.ingestion.table_pipeline import parse_table_region
    from tablerag.models.base import TableCtx, TableParse
    from tablerag.models.registry import get_double_read_provider
    from tablerag.models.table_parsing import run_table_verify

    info = await asyncio.to_thread(_table_region_inputs, element_id)
    if info is None:
        return None
    settings = get_settings()
    if info["spans_pages"]:
        # a merged cross-page table: its stored crop is the stitched image of
        # every fragment, and re-rendering one page would lose the rest of it
        crop, grid, dpi = info["crop"], None, None
    else:
        dpi = min(settings.table_crop_dpi * 2, 600)
        crop, grid = await asyncio.to_thread(
            _render_region, info["pdf"], info["page"], info["bbox"], dpi)

    # is_complex=True forces the VLM path: the simple grid path is what a
    # doubtful parse already went through, so re-running it proves nothing
    result = await parse_table_region(crop, grid, True, info["locale"])

    # --- the second look: a CHECK of the first, not a blind re-read ---
    # Given evidence (its own reading, faulted against the image) instead of
    # encouragement — encouragement is the one thing measured to make this model
    # worse. The correction answers under the same contract, so every structural
    # guard still applies to it, and a failed check costs nothing: the first
    # reading stands.
    second = None
    verified: TableParse | None = None
    if result.records and not result.error:
        verify_crop = crop
        if not info["spans_pages"] and settings.table_verify_dpi > dpi:
            verify_crop, _ = await asyncio.to_thread(
                _render_region, info["pdf"], info["page"], info["bbox"],
                settings.table_verify_dpi)
        verifier = get_double_read_provider() or get_provider("parser")
        try:
            verified = await run_table_verify(
                verifier.chat, ensure_min_width(verify_crop,
                                                settings.vlm_min_image_width),
                TableCtx(locale_hint=info["locale"] or "unknown"),
                result.html, result.records)
        except Exception:  # noqa: BLE001 — a failed check must not lose the read
            logger.exception("verification pass failed; keeping the first read")
        if verified is not None and verified.records:
            second = [r.model_dump() for r in verified.records]

    report = assess(result.html, result.records, second,
                    review_threshold=settings.confidence_review_threshold,
                    agreement_threshold=settings.double_read_agreement_threshold)

    # the check's output IS the proposal when it produced one: it is the first
    # reading plus whatever the image contradicted. The agreement below says how
    # much it changed, so the reviewer knows where to look.
    final_html = (verified.html if verified is not None else result.html) or ""
    final_records: list[dict] = (
        second if second is not None else list(result.records))
    return {
        "html": final_html,
        "records": [{"dimensions": r.get("dimensions", {}),
                     "metrics": r.get("metrics", {}),
                     "raw_values": r.get("raw_values", {})}
                    for r in final_records],
        "confidence": report.confidence,
        "signals": (report.detail or {}).get("signals") or {},
        "second_read": second is not None,
        "dpi": dpi,                      # None when the stitched crop was used
        "stitched": info["spans_pages"],
        "grid_hint": grid is not None,
        "error": result.error,
    }


def _element_locale(element_id: uuid.UUID) -> tuple[bool, str | None]:
    """(element exists, its KB's declared number locale)."""
    from tablerag.storage.orm import KnowledgeBase

    with session_scope() as s:
        element = s.get(Element, element_id)
        if element is None:
            return False, None
        document = s.get(Document, element.doc_id)
        kb = s.get(KnowledgeBase, document.kb_id) if document else None
        return True, (kb.config or {}).get("locale") if kb else None


async def derive_from_html(element_id: uuid.UUID, html: str) -> dict | None:
    """Rebuild records and summary from hand-corrected table HTML.

    Correcting the HTML alone leaves the element inconsistent in the worst
    possible way: a right-looking grid on screen while answers keep quoting
    numbers from the records built off the OLD parse. Records are re-derived
    deterministically (no model): the HTML is read into a grid with merged cells
    expanded — the same reading the answering context uses — and the existing
    simple-path builder splits dimensions from metrics, locale-aware.

    A PROPOSAL: returned for review, written only when the reviewer saves."""
    from tablerag.core.table_text import html_to_grid
    from tablerag.ingestion.table_pipeline import records_from_grid, summarize_table

    exists, locale = await asyncio.to_thread(_element_locale, element_id)
    if not exists:
        return None

    grid = html_to_grid(html)
    records: list[dict] = []
    if grid and len(grid) >= 2:
        try:
            records = records_from_grid(grid, locale)
        except Exception:  # noqa: BLE001 — a hand-edited grid can be anything
            records = []
    # the routing summary describes the table, so it goes stale with it
    summary = await summarize_table(html, locale)
    return {
        "records": [{"dimensions": r.get("dimensions", {}),
                     "metrics": r.get("metrics", {}),
                     "raw_values": r.get("raw_values", {})}
                    for r in records],
        "summary": summary or "",
        "rows": len(grid) if grid else 0,
        "cols": len(grid[0]) if grid else 0,
    }


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
