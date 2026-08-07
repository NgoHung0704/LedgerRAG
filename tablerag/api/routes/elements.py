"""Element detail + crop image — the citation click-through target
(principle #3: answer -> element -> crop image -> PDF page, always)."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from tablerag.core.schemas import (
    DeriveFromHtmlRequest,
    ElementAssistRequest,
    ElementEdit,
)
from tablerag.api.caching import stored_image
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


@router.delete("/{element_id}", status_code=204)
def delete_element(element_id: uuid.UUID) -> Response:
    """Drop one parsed element — a running header, a stray fragment, a block
    that only dilutes retrieval. Its chunks, records and vectors go with it.

    The original file is untouched, so reprocessing the document brings it back
    exactly as ingestion produced it; that is what makes this safe."""
    from tablerag.storage.qdrant import get_vector_store

    get_vector_store().delete_element(element_id)
    with session_scope() as s:
        crops = repo.delete_elements(s, [element_id])
    if not crops:
        raise HTTPException(404, "element not found")
    store = get_object_store()
    for key in crops:
        store.delete(key)
    return Response(status_code=204)


@router.post("/{element_id}/undo")
async def undo_element_edit(element_id: uuid.UUID) -> dict:
    """Put this element back the way it was before the last edit, and re-index.

    Reprocessing the document already undoes anything, but it re-runs the whole
    file and discards every other correction made to it. This takes back one
    element's last save — including "this is not a table", the one edit that
    destroys a representation outright."""
    from tablerag import indexing

    action = await asyncio.to_thread(indexing.undo_element_edit, element_id)
    if action is None:
        raise HTTPException(404, "element not found, or nothing to undo")
    await indexing.reindex_element(element_id)
    with session_scope() as s:
        detail = repo.get_element_detail(s, element_id)
    detail["crop_url"] = f"/api/elements/{element_id}/image"
    detail["undone"] = action
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


@router.post("/{element_id}/assist")
async def assist_element_edit(element_id: uuid.UUID,
                              body: ElementAssistRequest) -> dict:
    """An editing assistant for the content open in the editor.

    It works on what the reviewer is looking at (unsaved, so it travels with the
    request) and may rearrange it but never add facts — see models/edit_assist.
    Returns its reply plus, when it changed something, the complete new content
    as a PROPOSAL the reviewer applies by hand. Nothing is written."""
    from tablerag.models.edit_assist import assist

    def describe() -> str:
        """What the assistant is looking at — resolved here, not trusted from
        the client, so it cannot be told it is editing something else."""
        with session_scope() as s:
            detail = repo.get_element_detail(s, element_id)
        if detail is None:
            raise HTTPException(404, "element not found")
        kind = "a table" if detail.get("table") else f"a {detail['type']} block"
        return (f"{kind} from page {detail['page']} of "
                f"\"{detail['filename']}\"")

    where = await asyncio.to_thread(describe)
    # a long thread is not useful here and only eats context
    history = [(t.role, t.content) for t in body.history[-6:]]
    try:
        reply, proposal = await assist(body.format, body.content,
                                       body.instruction, history, where)
    except Exception as e:  # noqa: BLE001 — surface model failures readably
        raise HTTPException(502, f"the assistant could not answer: {e}") from e
    return {"reply": reply, "proposal": proposal}


@router.post("/{element_id}/derive")
async def derive_element_records(element_id: uuid.UUID,
                                 body: DeriveFromHtmlRequest) -> dict:
    """Rebuild this table's records and summary from the HTML being edited.

    Fixing the HTML by hand otherwise leaves the element inconsistent: a correct
    grid on screen while answers still quote numbers from records built off the
    old parse. Records are re-derived deterministically from the HTML; the
    summary is regenerated because it describes a table that just changed.
    Nothing is written — the reviewer saves."""
    from tablerag import indexing

    result = await indexing.derive_from_html(element_id, body.html)
    if result is None:
        raise HTTPException(404, "element not found")
    return result


@router.post("/{element_id}/recheck")
async def recheck_element(element_id: uuid.UUID) -> dict:
    """Parse this table again, harder — a proposal, nothing is written.

    The region is re-rendered from the PDF at double the ingest DPI, the
    text-layer grid is recovered as a hint, and the table is read twice so the
    reads can be scored against each other. The reviewer sees the agreement
    before deciding to save."""
    from tablerag import indexing

    proposal = await indexing.recheck_table(element_id)
    if proposal is None:
        raise HTTPException(
            404, "element not found, is not a table, or its source file is "
                 "no longer available")
    return proposal


@router.post("/{element_id}/split")
async def split_element_table(element_id: uuid.UUID) -> dict:
    """"These are two tables": break a region detection drew around both.

    Read as one, their rows land in a single set of records, and a question
    about the first table can be answered from a row of the second — wrong in
    the way that looks right. The model is asked only WHERE the seam is; each
    part is then re-rendered from the PDF and parsed through the ordinary
    contract, and gets its own bbox and crop.

    Undo puts the single table back and removes the parts."""
    from tablerag import indexing

    parts, reason = await indexing.split_table(element_id)
    if parts is None:
        # say which of the several ways this can end actually happened —
        # one message claiming the model decided was wrong about most of them
        raise HTTPException(409, f"Nothing was split: {reason}")
    with session_scope() as s:
        children = repo.split_children(s, element_id)
    await indexing.reindex_element(element_id)
    for child in children:
        await indexing.reindex_element(child)
    with session_scope() as s:
        detail = repo.get_element_detail(s, element_id)
    detail["crop_url"] = f"/api/elements/{element_id}/image"
    detail["parts"] = parts
    detail["reason"] = reason
    return detail


class MergeRequest(BaseModel):
    ids: list[uuid.UUID]


@router.post("/merge")
async def merge_element_tables(body: MergeRequest) -> dict:
    """"These are one table": join the chosen ones and re-parse.

    The inverse of "two tables". Detection splits a table wherever its ruling
    stops — a change of section, a band of colour, a page break it did not read
    as a continuation — and left apart, half the rows answer for the whole.

    WHICH tables is the reviewer's decision. This used to join with "the next
    table in reading order", which nobody could see, so nobody could tell what
    they were about to get.

    The first in reading order keeps its identity; undo restores its previous
    content, and the others are gone until the document is reprocessed."""
    from tablerag import indexing

    rows, reason = await indexing.merge_tables(body.ids)
    if rows is None:
        raise HTTPException(409, f"Nothing was joined: {reason}")
    # the survivor is whichever of the chosen ids still exists — the others
    # were merged into it and deleted
    with session_scope() as s:
        from tablerag.storage.orm import Element

        anchor = next((i for i in body.ids if s.get(Element, i) is not None),
                      None)
        if anchor is None:
            raise HTTPException(404, "the joined table no longer exists")
        detail = repo.get_element_detail(s, anchor)
    detail["crop_url"] = f"/api/elements/{anchor}/image"
    detail["reason"] = reason
    return detail


@router.post("/{element_id}/row-merging")
async def set_element_row_merging(element_id: uuid.UUID,
                                  merged: bool = True) -> dict:
    """Draw repeated values as one merged cell, or as one cell per row.

    Display only: records come from a forward-filled grid, so every row already
    carries its own value whichever way the HTML is written. Nothing is
    re-indexed and no answer changes — which is why this does not clear the
    review flag either."""
    from tablerag import indexing

    html = await asyncio.to_thread(indexing.set_row_merging, element_id, merged)
    if html is None:
        raise HTTPException(404, "element not found, or it has no table")
    with session_scope() as s:
        detail = repo.get_element_detail(s, element_id)
    detail["crop_url"] = f"/api/elements/{element_id}/image"
    return detail


@router.post("/{element_id}/convert-to-text")
async def convert_element_to_text(element_id: uuid.UUID) -> dict:
    """"This is not a table": demote a wrongly detected table to plain text.

    Detection sometimes fires on prose laid out in columns. The cells' own words
    become the element's text (nothing invented), the records and the grid go
    away, and it is re-indexed as text. The crop image stays, so provenance is
    intact, and reprocessing the document restores the table if detection was
    right after all."""
    from tablerag import indexing

    ok = await asyncio.to_thread(indexing.convert_table_to_text, element_id)
    if not ok:
        raise HTTPException(404, "element not found, or it is not a table")
    await indexing.reindex_element(element_id)
    with session_scope() as s:
        detail = repo.get_element_detail(s, element_id)
    detail["crop_url"] = f"/api/elements/{element_id}/image"
    return detail


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
def get_element_image(element_id: uuid.UUID, request: Request) -> Response:
    """The crop, which is the authority a reviewer reads the parse against.

    Its URL never changes but its CONTENT does: splitting a table rewrites the
    first part's crop in place, and so do joining, undo and reprocessing. With
    no cache headers a browser reuses the old picture heuristically, so a table
    cut in two went on showing the uncut image — the parse had changed and the
    evidence beside it had not, which is the one thing this image exists to
    prevent.

    no-cache is not "do not cache": it is "always ask". The ETag makes asking
    free — an unchanged crop comes back as a 304 with no body."""
    with session_scope() as s:
        from tablerag.storage.orm import Element

        element = s.get(Element, element_id)
        if element is None:
            raise HTTPException(404, "element not found")
        key = element.crop_image_path
    store = get_object_store()
    if not store.exists(key):
        raise HTTPException(404, "crop image not found")
    return stored_image(store.get(key),
                        request.headers.get("if-none-match"))
