"""Element detail + crop image — the citation click-through target
(principle #3: answer -> element -> crop image -> PDF page, always)."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from tablerag.core.schemas import ElementEdit
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope
from tablerag.storage.object_store import get_object_store

router = APIRouter(prefix="/api/elements", tags=["elements"])


@router.get("/{element_id}")
def get_element(element_id: uuid.UUID) -> dict:
    with session_scope() as s:
        detail = repo.get_element_detail(s, element_id)
    if detail is None:
        raise HTTPException(404, "element not found")
    detail["crop_url"] = f"/api/elements/{element_id}/image"
    return detail


@router.patch("/{element_id}")
async def edit_element(element_id: uuid.UUID, body: ElementEdit) -> dict:
    """Manual correction of a parsed element, then re-index so answers use the
    corrected data (SPEC §0.3 human-in-the-loop)."""
    from tablerag import indexing

    records = ([r.model_dump() for r in body.records]
               if body.records is not None else None)
    ok = await asyncio.to_thread(
        indexing.apply_element_edit, element_id,
        text=body.text, html=body.html, summary=body.summary, records=records)
    if not ok:
        raise HTTPException(404, "element not found")
    await indexing.reindex_element(element_id)
    with session_scope() as s:
        detail = repo.get_element_detail(s, element_id)
    detail["crop_url"] = f"/api/elements/{element_id}/image"
    return detail


@router.post("/{element_id}/reread")
async def reread_element(element_id: uuid.UUID, mode: str = "structure") -> dict:
    """Have the parser VLM re-read this element's PAGE.

    `mode` picks what comes back (see ocr.REREAD_MODES): a faithful transcription
    that keeps a grid/diagram as a markdown table, an explanation of what the
    page says, or both. A column layout reads as a 2-D grid that linear
    extraction flattens, and no reading order recovers it.

    This returns a PROPOSAL and writes nothing: the reviewer compares it against
    the original image and saves it through the normal element edit, which
    re-chunks and re-indexes."""
    from tablerag.core.config import get_settings
    from tablerag.ingestion.imaging import ensure_min_width
    from tablerag.ingestion.ocr import REREAD_MODES, reread_page
    from tablerag.storage.object_store import page_image_key
    from tablerag.storage.orm import Document, Element

    if mode not in REREAD_MODES:
        raise HTTPException(
            400, f"unknown mode {mode!r}; expected one of "
                 f"{', '.join(sorted(REREAD_MODES))}")

    def load() -> bytes:
        with session_scope() as s:
            element = s.get(Element, element_id)
            if element is None:
                raise HTTPException(404, "element not found")
            document = s.get(Document, element.doc_id)
            if document is None:
                raise HTTPException(404, "document not found")
            key = page_image_key(document.kb_id, element.doc_id, element.page)
        store = get_object_store()
        if not store.exists(key):
            raise HTTPException(404, "page image not found")
        return store.get(key)

    # the WHOLE page, not the text crop: the VLM needs the panels, arrows and
    # headings around the text to reconstruct what belongs with what
    page_png = await asyncio.to_thread(load)
    page_png = ensure_min_width(page_png, get_settings().vlm_min_image_width)
    text = await reread_page(page_png, mode)
    if not text:
        raise HTTPException(502, "the parser model returned nothing")
    return {"text": text, "mode": mode}


@router.post("/{element_id}/approve")
def approve_element(element_id: uuid.UUID) -> dict:
    """Review flow: admin confirmed the parse — clear the needs_review flag;
    answers using this table return to normal (Phase 3 DoD)."""
    with session_scope() as s:
        element = repo.approve_element(s, element_id)
        if element is None:
            raise HTTPException(404, "element not found")
        detail = repo.get_element_detail(s, element_id)
    detail["crop_url"] = f"/api/elements/{element_id}/image"
    return detail


@router.post("/{element_id}/unusable")
def mark_element_unusable(element_id: uuid.UUID) -> dict:
    """Review flow: admin rejected the parse — records leave retrieval, the
    original image stays for the honest fallback."""
    with session_scope() as s:
        element = repo.mark_element_unusable(s, element_id)
        if element is None:
            raise HTTPException(404, "element not found")
        detail = repo.get_element_detail(s, element_id)
    from tablerag.storage.qdrant import get_vector_store

    get_vector_store().delete_element(element_id)
    detail["crop_url"] = f"/api/elements/{element_id}/image"
    return detail


@router.get("/{element_id}/image")
def get_element_image(element_id: uuid.UUID) -> Response:
    with session_scope() as s:
        from tablerag.storage.orm import Element

        element = s.get(Element, element_id)
        if element is None:
            raise HTTPException(404, "element not found")
        key = element.crop_image_path
    store = get_object_store()
    if not store.exists(key):
        raise HTTPException(404, "crop image not found")
    return Response(content=store.get(key), media_type="image/png")
