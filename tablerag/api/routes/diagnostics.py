"""Diagnostics: inspect table DETECTION on an uploaded PDF without ingesting
it. Lets an admin debug a missing real-document table from the browser (no
shell access, no storage) — the file is analyzed in memory and discarded.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, UploadFile

from tablerag.ingestion.layout import diagnose_pdf_tables

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

MAX_BYTES = 50 * 1024 * 1024


@router.post("/table-detection")
async def table_detection(file: UploadFile) -> dict:
    """Per-page, per-strategy find_tables breakdown + what detection keeps."""
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
    return {"filename": file.filename, "page_count": len(pages), "pages": pages}
