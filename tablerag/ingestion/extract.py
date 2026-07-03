"""PDF page extraction (PyMuPDF).

Phase 1 heuristic (SPEC): PDFs with a text layer are extracted directly; a
page with almost no extractable text is flagged `needs_ocr` and left for the
Phase 2 VLM path. Every page is also rendered to PNG — cheap, and it is the
crop image that principle #3 requires every element to have.
"""

from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF


class PdfError(Exception):
    """Human-readable ingestion failure (constraint C4)."""


@dataclass
class PageExtract:
    page: int  # 1-based
    text: str
    needs_ocr: bool
    image_png: bytes
    width: float
    height: float


def extract_pages(pdf_bytes: bytes, dpi: int = 120,
                  min_chars_per_page: int = 32) -> list[PageExtract]:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise PdfError(f"The file could not be opened as a PDF ({e}).") from e

    pages: list[PageExtract] = []
    with doc:
        if doc.page_count == 0:
            raise PdfError("The PDF contains no pages.")
        for i, page in enumerate(doc):
            text = page.get_text("text")
            pixmap = page.get_pixmap(dpi=dpi)
            rect = page.rect
            pages.append(PageExtract(
                page=i + 1,
                text=text,
                needs_ocr=len(text.strip()) < min_chars_per_page,
                image_png=pixmap.tobytes("png"),
                width=rect.width,
                height=rect.height,
            ))
    return pages
