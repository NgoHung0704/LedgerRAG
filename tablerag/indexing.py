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
        # what it held before this save, so the save can be taken back
        repo.snapshot_element(s, element_id, "edit")
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
        # the grid and its records are about to go: this is the one edit that
        # destroys a representation outright, so it must be recoverable
        repo.snapshot_element(s, element_id, "convert-to-text")
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


async def convert_text_to_table(element_id: uuid.UUID, source: str):
    """Promote a text element to a real table, from markdown or HTML.

    The inverse of convert_table_to_text, and the missing half of it. A page
    laid out as a grid comes out of extraction as flattened prose; the VLM
    re-read turns it back into a markdown table, but until now that markdown
    could only be saved as TEXT — so a table the reviewer had just recovered
    stayed unsearchable as a table, with no records and no routing summary.

    The source is what is open in the editor, unsaved, so it travels with the
    request. Records and summary are built the ordinary way from the grid, so a
    table made here is indexed exactly like one detected at ingest.

    Returns (rows, reason); rows is None when nothing was converted."""
    from tablerag.core.table_text import html_to_grid, markdown_table_to_grid
    from tablerag.ingestion.table_pipeline import (
        grid_display_html,
        records_from_grid,
        summarize_table,
    )

    exists, locale = await asyncio.to_thread(_element_locale, element_id)
    if not exists:
        return None, "element not found"
    grid = (html_to_grid(source) if "<table" in (source or "").lower()
            else markdown_table_to_grid(source))
    if not grid or len(grid) < 2 or len(grid[0]) < 2:
        return None, ("no table was found in this content — a markdown pipe "
                      "table or an HTML <table> is needed, with a header row "
                      "and at least one row under it")

    html = grid_display_html(grid)
    try:
        records = records_from_grid(grid, locale)
    except Exception:  # noqa: BLE001 — hand-written content can be anything
        records = []
    summary = await summarize_table(html, locale)
    ok = await asyncio.to_thread(_write_text_to_table, element_id, html,
                                 records, summary, len(grid), len(grid[0]))
    if not ok:
        return None, "this element is not a text element"
    return len(grid) - 1, (f"converted into a table of {len(grid) - 1} rows "
                           f"and {len(grid[0])} columns")


def _write_text_to_table(element_id: uuid.UUID, html: str, records: list,
                         summary: str | None, rows: int, cols: int) -> bool:
    with session_scope() as s:
        element = s.get(Element, element_id)
        if element is None or element.type != "text":
            return False
        # undo puts the text back: the snapshot holds it, and restoring a text
        # element re-chunks from it
        repo.snapshot_element(s, element_id, "convert-to-table")
        # its chunks go: a table is retrieved through its records and its
        # summary, and leaving them would index the same content twice
        for chunk in list(element.chunks):
            s.delete(chunk)
        s.flush()
        element.type = "table"
        element.needs_review = False
        element.meta = {**(element.meta or {}), "edited": True,
                        "converted_from": "text"}
        repo.add_table_element(s, element_id, html or None, summary or None,
                               rows, cols, "manual")
        if records:
            repo.add_records(s, element_id, [
                {**r, "text_repr": build_text_repr(
                    r.get("dimensions", {}), r.get("metrics", {}),
                    r.get("raw_values", {}))}
                for r in records])
    return True


def set_row_merging(element_id: uuid.UUID, merged: bool) -> str | None:
    """Show repeated values as one merged cell, or as one cell per row.

    A guarantee table prints "300 %BRSS" once against two kinds of care, and
    collapsing that into a rowspan is what the page looks like. But it is not
    always what a reader wants: a merged cell is harder to scan across, harder
    to copy a single row out of, and it hides how many rows a value covers.

    This is a DISPLAY change and nothing more. Records are built from a
    forward-filled grid, so every row already carries its own value whichever
    way the HTML is written — nothing is re-indexed and no answer moves. The
    reading is round-tripped through the same expander the answering context
    uses, so the two can never disagree about what the table says.

    Returns the new HTML, or None when there is no table to change."""
    from tablerag.core.table_text import html_to_grid
    from tablerag.ingestion.html_tables import collapse_vertical_merges
    from tablerag.ingestion.table_pipeline import _grid_to_html

    with session_scope() as s:
        table = s.get(TableElement, element_id)
        if table is None or not table.html:
            return None
        grid = html_to_grid(table.html)
        if not grid:
            return None
        html = _grid_to_html(grid)
        if merged:
            html = collapse_vertical_merges(html) or html
        if html == table.html:
            return html                       # already the way it was asked for
        # undo covers it like any other change to stored content; needs_review
        # is left alone, because how a table is DRAWN says nothing about
        # whether its parse was checked
        repo.snapshot_element(s, element_id, "row-merging")
        table.html = html
    return html


def _drop_crops(keys: list[str], keep: str | None = None) -> None:
    from tablerag.storage.object_store import get_object_store

    store = get_object_store()
    for key in keys:
        if key and key != keep:
            store.delete(key)


def undo_element_edit(element_id: uuid.UUID) -> str | None:
    """Put the element back the way it was before the last edit.

    Returns the action that was undone, or None when there is nothing to undo.
    A table demoted to text comes back as a table, grid and records included —
    that is the edit worth being able to take back, since it is the only one
    that destroys a representation outright.

    Plain stack semantics: each edit pushes the state before it, undo pops one
    and restores it, so pressing it again walks further back. There is no redo
    — a toggle would make "undo, undo" mean nothing, and walking back through
    real history is the more useful of the two."""
    with session_scope() as s:
        element = s.get(Element, element_id)
        if element is None:
            return None
        previous = repo.pop_revision(s, element_id)
        if previous is None:
            return None

        if previous["action"] == "split":
            # the parts that were carved off go with it, or undo would leave
            # the first table restored to its full range AND its siblings
            # still standing — the same rows indexed twice
            siblings = repo.split_children(s, element_id)
            if siblings:
                keys = repo.delete_elements(s, siblings)
                _drop_crops(keys, keep=element.crop_image_path)

        element.type = previous["element_type"]
        element.needs_review = previous["needs_review"]
        element.meta = {**(element.meta or {}), "edited": True}
        _rechunk(s, element, previous["text"] or "")

        table = s.get(TableElement, element_id)
        if previous["html"] is None and previous["records"] is None:
            if table is not None:
                s.delete(table)          # it was a text element before
                s.flush()
        else:
            if table is None:            # a demoted table coming back
                table = repo.add_table_element(s, element_id, None, None,
                                               None, None, "restored")
            table.html = previous["html"]
            table.summary = previous["summary"]
            _replace_records(s, element_id, previous["records"] or [])
    return previous["action"]


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
                "span_pages": list(meta.get("span_pages") or []),
                "crop_key": element.crop_image_path}
    store = get_object_store()
    if info["spans_pages"] and store.exists(info["crop_key"]):
        info["crop"] = store.get(info["crop_key"])
    # an Office document was ingested through its cached PDF rendering
    if needs_conversion(info["filename"]):
        info["key"] = doc_converted_pdf_key(info["kb_id"], info["doc_id"])
    # the PDF is loaded for a stitched table too: recheck reads it from the
    # stitched crop, but taking a wrong MERGE apart needs each page again
    if store.exists(info["key"]):
        info["pdf"] = store.get(info["key"])
    elif not info.get("crop"):
        return None
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


def _region_rows(pdf_bytes: bytes, page_no: int,
                 bbox: list[float]) -> tuple[list[list[str | None]] | None,
                                             list[float]]:
    """The region's grid AND the y coordinate of each row's top edge.

    Splitting a wrongly merged region needs both: the model says which row
    starts the second table, and the PDF says where that row is on the page —
    so each part gets a real bbox and a real crop of its own rather than a
    shared picture of the pair (principle #3)."""
    import fitz

    from tablerag.ingestion.layout import detect_tables

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc[page_no - 1]
        clip = fitz.Rect(*bbox) if len(bbox) == 4 else page.rect
        # EVERY table under the region, not just the biggest: an element that
        # wrongly holds two of them overlaps two detections, and taking only
        # the larger left the seam outside the rows we knew about — the split
        # then found nothing to cut and gave up without saying why
        parts = []
        for table, candidate in detect_tables(page):
            rect = fitz.Rect(table.bbox) & clip
            if not rect.is_empty and candidate:
                parts.append((float(table.bbox[1]), candidate,
                              [float(row.bbox[1]) for row in table.rows]))
        parts.sort()
        grid = [row for _, candidate, _ in parts for row in candidate] or None
        tops = [top for _, _, rows in parts for top in rows]
    return grid, tops


async def merge_tables(element_ids: list[uuid.UUID]):
    """Join the CHOSEN tables into one — the inverse of "two tables".

    Detection splits a table wherever its ruling stops: a change of section, a
    band of colour, a page break it did not read as a continuation. Left apart,
    half the rows answer for the whole while the header lives on one piece.

    Which tables is the reviewer's decision, not a guess. It used to join with
    "the next table in reading order", and nobody could see what that was.

    Returns (rows, reason); rows is None when nothing was joined."""
    from tablerag.ingestion.imaging import stitch_vertical
    from tablerag.ingestion.table_pipeline import parse_table_region

    parts, refusal = await asyncio.to_thread(_tables_to_join, element_ids)
    if parts is None:
        return None, refusal
    anchor = parts[0]
    info = await asyncio.to_thread(_table_region_inputs, anchor["id"])
    if info is None or "pdf" not in info:
        return None, ("the source file is no longer available, so the joined "
                      "region cannot be read again")

    # one region per page, then stitched in page order. A same-page join is
    # simply the case where there is one of them, so there is no second code
    # path to keep in step — and a selection spanning a page break, which is
    # what a table cut by one looks like, works without being special.
    settings = get_settings()
    by_page: dict[int, list[float]] = {}
    for part in parts:
        box = by_page.get(part["page"])
        if box is None:
            by_page[part["page"]] = list(part["bbox"])
        else:
            box[0], box[1] = min(box[0], part["bbox"][0]), min(box[1], part["bbox"][1])
            box[2], box[3] = max(box[2], part["bbox"][2]), max(box[3], part["bbox"][3])

    pages = sorted(by_page)
    rendered = [await asyncio.to_thread(_render_region, info["pdf"], page,
                                        by_page[page], settings.table_crop_dpi)
                for page in pages]
    crop, grid = rendered[0]
    for other, _ in rendered[1:]:
        crop, grid = stitch_vertical(crop, other), None

    result = await parse_table_region(crop, grid, True, info["locale"])
    await asyncio.to_thread(
        _write_merge, anchor["id"], [p["id"] for p in parts[1:]], info,
        pages[0], by_page[pages[0]], crop, result,
        pages if len(pages) > 1 else [])
    where = (f"across pages {', '.join(str(p) for p in pages)}"
             if len(pages) > 1 else f"on page {pages[0]}")
    return result.n_rows, (f"joined {len(parts)} tables {where} into one of "
                           f"{result.n_rows} rows")


def _tables_to_join(element_ids: list[uuid.UUID]):
    """The chosen elements in reading order, or (None, why not).

    Reading order is (page, top edge) rather than the order they were clicked:
    a stitched crop must run down the document, however the reviewer selected
    it."""
    with session_scope() as s:
        picked = [s.get(Element, eid) for eid in element_ids]
        if len(picked) < 2 or any(e is None for e in picked):
            return None, "choose at least two tables to join"
        if any(e.type != "table" for e in picked):
            return None, "only tables can be joined"
        if len({e.doc_id for e in picked}) != 1:
            return None, "the tables must all come from the same document"
        picked.sort(key=lambda e: (e.page, (e.bbox or [0, 0])[1]))
        return [{"id": e.id, "page": e.page, "bbox": list(e.bbox or [])}
                for e in picked], None


def _write_merge(element_id: uuid.UUID, others: list, info: dict,
                 page: int, bbox, crop: bytes, result, spans: list[int]) -> None:
    from tablerag.storage.object_store import get_object_store

    store = get_object_store()
    with session_scope() as s:
        element = s.get(Element, element_id)
        if element is None:
            return
        repo.snapshot_element(s, element_id, "merge")
        store.put(element.crop_image_path, crop, "image/png")
        element.page, element.bbox = page, list(bbox)
        element.needs_review = result.needs_review
        meta = {**(element.meta or {}), "edited": True, "merged": True}
        if spans:
            meta["span_pages"] = spans
        else:
            meta.pop("span_pages", None)
        element.meta = meta

        table = s.get(TableElement, element_id)
        if table is None:
            table = repo.add_table_element(s, element_id, None, None, None,
                                           None, result.parse_strategy)
        table.html = result.html or None
        table.summary = None          # it described half of it
        table.n_rows, table.n_cols = result.n_rows, result.n_cols
        _replace_records(s, element_id, result.records or [])

        keys = repo.delete_elements(s, others)
        _drop_crops(keys, keep=element.crop_image_path)


def _page_table_region(pdf_bytes: bytes, page_no: int,
                       first: bool) -> list[float] | None:
    """The fragment on one page of a table that was merged across pages.

    Chosen exactly the way the merge chose it: the BOTTOM-most table on the
    page where it started, the TOP-most on each page it continued onto. Taking
    the merge apart is deterministic — the seam is the page boundary, so there
    is no judgement to ask a model for and none to get wrong."""
    import fitz

    from tablerag.ingestion.layout import detect_tables

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if not 0 < page_no <= doc.page_count:
            return None
        found = [fitz.Rect(t.bbox) for t, _ in detect_tables(doc[page_no - 1])]
    if not found:
        return None
    box = (max(found, key=lambda r: r.y1) if first
           else min(found, key=lambda r: r.y0))
    return [box.x0, box.y0, box.x1, box.y1]


async def _split_by_page(element_id: uuid.UUID, info: dict):
    """Undo a cross-page merge: one element per page it covered."""
    from tablerag.ingestion.table_pipeline import parse_table_region

    pages = info["span_pages"]
    if len(pages) < 2 or "pdf" not in info:
        return None, ("this table is recorded as spanning pages, but its "
                      "source file is no longer available to take apart")
    settings = get_settings()
    results = []
    for index, page in enumerate(pages):
        box = await asyncio.to_thread(_page_table_region, info["pdf"], page,
                                      index == 0)
        if box is None:
            return None, (f"no table could be found again on page {page}; "
                          f"reprocess the document instead")
        crop, grid = await asyncio.to_thread(
            _render_region, info["pdf"], page, box, settings.table_crop_dpi)
        results.append((page, box, crop,
                        await parse_table_region(crop, grid, True,
                                                 info["locale"])))

    await asyncio.to_thread(_write_split, element_id, info, results)
    return len(results), (f"unmerged into {len(results)} tables, one per page "
                          f"({', '.join(str(p) for p in pages)})")


def _write_split(element_id: uuid.UUID, info: dict, results: list) -> None:
    """First part replaces the element; the rest become new elements beside it.

    Each carries its own bbox and its own crop, so a split table is
    indistinguishable from two tables that were detected separately — which is
    what they should have been."""
    from tablerag.ingestion.tasks import element_image_key
    from tablerag.storage.object_store import get_object_store

    store = get_object_store()
    with session_scope() as s:
        element = s.get(Element, element_id)
        if element is None:
            return
        repo.snapshot_element(s, element_id, "split")

        first_page, first_box, first_crop, first = results[0]
        store.put(element.crop_image_path, first_crop, "image/png")
        element.page = first_page
        element.bbox = first_box
        element.needs_review = first.needs_review
        meta = {**(element.meta or {}), "edited": True, "split": True}
        # it no longer spans anything: leaving the mark would send recheck back
        # to a stitched crop that has just been replaced
        meta.pop("span_pages", None)
        element.meta = meta
        table = s.get(TableElement, element_id)
        if table is None:
            table = repo.add_table_element(s, element_id, None, None, None,
                                           None, first.parse_strategy)
        table.html = first.html or None
        table.summary = None       # it described the pair; it is wrong now
        table.n_rows, table.n_cols = first.n_rows, first.n_cols
        _replace_records(s, element_id, first.records or [])

        for page, box, crop, part in results[1:]:
            new_id = uuid.uuid4()
            key = element_image_key(info["kb_id"], info["doc_id"], new_id)
            store.put(key, crop, "image/png")
            repo.add_element(
                s, info["doc_id"], page, bbox=box, type_="table",
                crop_image_path=key, confidence=None,
                needs_review=part.needs_review,
                meta={"split_from": str(element_id)}, element_id=new_id)
            repo.add_table_element(s, new_id, part.html or None, None,
                                   part.n_rows, part.n_cols,
                                   part.parse_strategy)
            if part.records:
                repo.add_records(s, new_id, [
                    {**r, "text_repr": build_text_repr(
                        r.get("dimensions", {}), r.get("metrics", {}),
                        r.get("raw_values", {}))}
                    for r in part.records])


def split_bboxes(bbox: list[float], row_tops: list[float],
                 seams: list[int]) -> list[list[float]]:
    """Cut a region's bbox at the given row numbers (1-based, each starting a
    new table). Returns one bbox per part, top to bottom."""
    x0, y0, x1, y1 = bbox
    cuts = [row_tops[row - 1] for row in seams
            if 0 < row <= len(row_tops) and y0 < row_tops[row - 1] < y1]
    edges = [y0, *sorted(cuts), y1]
    return [[x0, top, x1, bottom]
            for top, bottom in zip(edges, edges[1:]) if bottom - top > 1.0]


async def split_table(element_id: uuid.UUID) -> int | None:
    """Break a region that holds two tables into one element per table.

    Detection sometimes draws one box around two tables printed one under
    another. Read as one, their rows land in a single set of records, and a
    question about the first can be answered from a row of the second — wrong
    in the way that looks right.

    The model is asked only WHERE the seam is; each part is then re-rendered
    from the PDF and parsed through the ordinary contract, so every guard that
    applies to a table applies to these. Parts after the first become new
    elements carrying `split_from`, and the whole thing is recorded on the
    revision stack, so undo puts the single table back and removes them.

    Returns (parts, reason). `parts` is None when nothing was split, and
    `reason` always says WHY — five different situations end here, and one
    message claiming the model decided was wrong about four of them."""
    from tablerag.ingestion.table_pipeline import parse_table_region
    from tablerag.models.base import Msg
    from tablerag.models.registry import get_provider
    from tablerag.models.table_parsing import (
        SPLIT_PROMPT,
        numbered_rows,
        parse_split_rows,
    )

    info = await asyncio.to_thread(_table_region_inputs, element_id)
    if info is None:
        return None, ("this table's source file is no longer available, so "
                      "its region cannot be re-read")
    if info["spans_pages"]:
        # the seam IS the page boundary — no model needed, and no judgement to
        # get wrong. This is the case the feature was asked for: two tables on
        # facing pages with the SAME header and the same columns read as one
        # long table, when the second is simply another table.
        return await _split_by_page(element_id, info)
    settings = get_settings()
    grid, row_tops = await asyncio.to_thread(
        _region_rows, info["pdf"], info["page"], info["bbox"])
    if not grid or len(row_tops) < 4:
        return None, ("no row grid was found under this region — it has no "
                      "text layer (a scan), so there are no row positions to "
                      "cut at")

    parser = get_provider("parser")
    prompt = SPLIT_PROMPT.replace("{rows}", numbered_rows(grid))
    answer = []
    async for token in parser.chat([Msg(role="user", content=prompt)],
                                   stream=True, temperature=0.0):
        answer.append(token)
    reply = "".join(answer)
    seams = parse_split_rows(reply, len(grid))
    logger.info("split %s: %d rows, model said %r -> seams %s",
                element_id, len(grid), reply.strip()[:120], seams)
    if not seams:
        return None, ("the model read these %d rows as one table — it found "
                      "no second header or change of subject" % len(grid))

    boxes = split_bboxes(info["bbox"], row_tops, seams)
    if len(boxes) < 2:
        return None, (f"the model put the seam at row {seams[0]}, but that "
                      f"row is not inside this element's own region — nothing "
                      f"could be cut")

    dpi = settings.table_crop_dpi
    results = []
    for box in boxes:
        crop, sub_grid = await asyncio.to_thread(
            _render_region, info["pdf"], info["page"], box, dpi)
        results.append((info["page"], box, crop, await parse_table_region(
            crop, sub_grid, True, info["locale"])))

    await asyncio.to_thread(_write_split, element_id, info, results)
    return len(results), (f"cut at row {', '.join(str(r) for r in seams)} into "
                          f"{len(results)} tables")


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
    from tablerag.models.base import TableCtx
    from tablerag.models.registry import get_double_read_provider
    from tablerag.models.table_parsing import (
        format_grid_hint,
        run_table_verify,
    )

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
    corrected = None
    findings, clean = "", False
    if result.records and not result.error:
        verify_crop = crop
        if not info["spans_pages"] and settings.table_verify_dpi > dpi:
            verify_crop, _ = await asyncio.to_thread(
                _render_region, info["pdf"], info["page"], info["bbox"],
                settings.table_verify_dpi)
        verifier = get_double_read_provider() or get_provider("parser")
        try:
            check = await run_table_verify(
                verifier.chat, ensure_min_width(verify_crop,
                                                settings.vlm_min_image_width),
                TableCtx(locale_hint=info["locale"] or "unknown"),
                result.html, result.records,
                # the text layer's own values: catching a misread digit is a
                # comparison, not an act of attention
                grid_hint=format_grid_hint(grid))
            corrected, findings, clean = check.parse, check.findings, check.clean
        except Exception:  # noqa: BLE001 — a failed check must not lose the read
            logger.exception("verification pass failed; keeping the first read")
        if corrected is not None and corrected.records:
            second = [r.model_dump() for r in corrected.records]

    report = assess(result.html, result.records, second,
                    review_threshold=settings.confidence_review_threshold,
                    agreement_threshold=settings.double_read_agreement_threshold)

    # the check's output IS the proposal when it produced one: it is the first
    # reading plus whatever the image contradicted. The agreement below says how
    # much it changed, so the reviewer knows where to look.
    final_html = (corrected.html if corrected is not None else result.html) or ""
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
        # what the check says is wrong, verbatim — the reviewer's map of where
        # to look. `clean` means it examined the reading and faulted nothing.
        "findings": findings,
        "clean": clean,
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
