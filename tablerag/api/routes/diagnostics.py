"""Diagnostics: inspect table DETECTION on an uploaded PDF without ingesting
it. Lets an admin debug a missing real-document table from the browser (no
shell access, no storage) — the file is analyzed in memory and discarded.

Two probes:
- find_tables breakdown per page/strategy (text-layer detection)
- optional VLM region detection on ONE page (`vlm_page` form field) — shows
  the raw model reply + the parsed boxes, for scanned pages where find_tables
  is blind. One VLM call, so it is per-page on demand, not for all pages.
"""

from __future__ import annotations

import asyncio

import fitz
from fastapi import APIRouter, Form, HTTPException, UploadFile

from tablerag.core.config import get_settings
from tablerag.ingestion.imaging import ensure_min_width
from tablerag.ingestion.layout import diagnose_pdf_tables
from tablerag.ingestion.region_detect import detect_table_regions_debug

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

MAX_BYTES = 50 * 1024 * 1024


@router.post("/table-detection")
async def table_detection(file: UploadFile,
                          vlm_page: int | None = Form(None)) -> dict:
    """Per-page, per-strategy find_tables breakdown (+ optional VLM region
    detection on one page)."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File exceeds the 50 MB diagnostics limit.")
    try:
        pages = await asyncio.to_thread(diagnose_pdf_tables, data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not analyze the PDF: {e}") from e

    result = {"filename": file.filename, "page_count": len(pages), "pages": pages}

    if vlm_page is not None:
        if not 1 <= vlm_page <= len(pages):
            raise HTTPException(400, f"vlm_page out of range (1..{len(pages)})")
        settings = get_settings()

        def render() -> bytes:
            with fitz.open(stream=data, filetype="pdf") as doc:
                png = doc[vlm_page - 1].get_pixmap(
                    dpi=settings.page_render_dpi).tobytes("png")
            return ensure_min_width(png, settings.vlm_min_image_width)

        image = await asyncio.to_thread(render)
        try:
            boxes, raw = await detect_table_regions_debug(image)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"VLM region detection failed: {e}") from e
        result["vlm"] = {
            "page": vlm_page,
            "count": len(boxes),
            "boxes": [[round(c, 3) for c in b] for b in boxes],
            "raw": raw[:2000],
        }
    return result
