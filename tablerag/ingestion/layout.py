"""Layout analysis: split each page into text / table / figure regions.

Detector choice (documented deviation from the spec's PP-Structure default):
for pages WITH a text layer, PyMuPDF's built-in `find_tables` is used — it is
even cheaper than PP-Structure, needs zero extra dependencies, and gives the
grid content for the simple-parser path for free. Scanned pages carry no text
layer, so they take the VLM path entirely (spec Phase 2 §6). If a future
corpus defeats find_tables, a PP-Structure detector can be swapped in behind
`analyze_document` without touching the rest of the pipeline.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import fitz  # PyMuPDF
from PIL import Image

from tablerag.ingestion.extract import PdfError

# image blocks smaller than this fraction of the page are decorations, not figures
_MIN_FIGURE_AREA_RATIO = 0.005
_CAPTION_MAX_DISTANCE = 60.0  # points below the figure
_CAPTION_MAX_CHARS = 300


@dataclass
class Region:
    type: str  # 'text' | 'table' | 'figure'
    bbox: tuple[float, float, float, float]
    text: str = ""                                  # text regions
    grid: list[list[str | None]] | None = None      # tables: simple-path extraction
    complex: bool = False                           # tables: classifier verdict
    caption: str | None = None                      # figures


@dataclass
class PageLayout:
    page: int  # 1-based
    width: float
    height: float
    image_png: bytes
    is_scan: bool
    regions: list[Region] = field(default_factory=list)


def table_grid_is_complex(grid: list[list[str | None]] | None) -> bool:
    """simple_parser vs vlm classifier — biased toward VLM on any doubt
    (SPEC Phase 2 §2: more expensive but more correct)."""
    if not grid or len(grid) < 2:
        return True
    n_cols = len(grid[0])
    if n_cols < 2:
        return True
    if any(len(row) != n_cols for row in grid):
        return True
    header = grid[0]
    if any(cell is None or not str(cell).strip() for cell in header):
        return True  # gaps in the header usually mean merged multi-level headers
    cells = [cell for row in grid for cell in row]
    empty = sum(1 for cell in cells if cell is None or not str(cell).strip())
    if empty / len(cells) > 0.15:
        return True  # merged/spanned cells surface as empty cells in the grid
    return False


def _overlap_ratio(rect: fitz.Rect, other: fitz.Rect) -> float:
    inter = fitz.Rect(rect) & other
    area = rect.get_area()
    return inter.get_area() / area if area else 0.0


def analyze_page(page: fitz.Page, dpi: int, min_chars: int) -> PageLayout:
    text = page.get_text("text")
    png = page.get_pixmap(dpi=dpi).tobytes("png")
    rect = page.rect
    layout = PageLayout(page=page.number + 1, width=rect.width,
                        height=rect.height, image_png=png,
                        is_scan=len(text.strip()) < min_chars)
    if layout.is_scan:
        return layout  # no text layer: the whole page goes down the VLM path

    # --- tables ---
    table_rects: list[fitz.Rect] = []
    try:
        tables = page.find_tables().tables
    except Exception:  # noqa: BLE001 — a detector crash must not kill the page
        tables = []
    for table in tables:
        grid = table.extract()
        if not grid or (len(grid) == 1 and len(grid[0]) <= 1):
            continue  # degenerate detection
        layout.regions.append(Region(
            type="table", bbox=tuple(table.bbox), grid=grid,
            complex=table_grid_is_complex(grid)))
        table_rects.append(fitz.Rect(table.bbox))

    # --- text + figures (blocks not covered by a table) ---
    blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, no, type)
    text_blocks = [b for b in blocks if b[6] == 0]
    text_parts: list[str] = []
    text_bbox: fitz.Rect | None = None
    figures: list[Region] = []

    for block in blocks:
        block_rect = fitz.Rect(block[:4])
        if any(_overlap_ratio(block_rect, tr) > 0.5 for tr in table_rects):
            continue
        if block[6] == 1:  # image block
            if block_rect.get_area() >= _MIN_FIGURE_AREA_RATIO * rect.get_area():
                figures.append(Region(type="figure", bbox=tuple(block_rect)))
            continue
        content = block[4].strip()
        if content:
            text_parts.append(content)
            text_bbox = block_rect if text_bbox is None else text_bbox | block_rect

    # nearest short text block below each figure = its caption (C5: keep
    # image + caption, nothing more)
    for figure in figures:
        fig_rect = fitz.Rect(figure.bbox)
        best, best_dy = None, _CAPTION_MAX_DISTANCE
        for block in text_blocks:
            content = block[4].strip()
            if not content or len(content) > _CAPTION_MAX_CHARS:
                continue
            block_rect = fitz.Rect(block[:4])
            dy = block_rect.y0 - fig_rect.y1
            horizontal = block_rect.x0 < fig_rect.x1 and block_rect.x1 > fig_rect.x0
            if 0 <= dy < best_dy and horizontal:
                best, best_dy = content, dy
        figure.caption = best

    if text_parts:
        layout.regions.append(Region(
            type="text", bbox=tuple(text_bbox), text="\n\n".join(text_parts)))
    layout.regions.extend(figures)
    layout.regions.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
    return layout


def analyze_document(pdf_bytes: bytes, dpi: int, min_chars: int) -> list[PageLayout]:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise PdfError(f"The file could not be opened as a PDF ({e}).") from e
    with doc:
        if doc.page_count == 0:
            raise PdfError("The PDF contains no pages.")
        return [analyze_page(page, dpi, min_chars) for page in doc]


def crop_region_png(page_png: bytes, page_width: float,
                    bbox: tuple[float, float, float, float], pad: float = 6.0) -> bytes:
    """Crop a region (PDF-point bbox) out of the rendered page PNG."""
    with Image.open(io.BytesIO(page_png)) as img:
        scale = img.width / page_width
        x0 = max(0, int((bbox[0] - pad) * scale))
        y0 = max(0, int((bbox[1] - pad) * scale))
        x1 = min(img.width, int((bbox[2] + pad) * scale))
        y1 = min(img.height, int((bbox[3] + pad) * scale))
        if x1 <= x0 or y1 <= y0:
            return page_png
        out = io.BytesIO()
        img.crop((x0, y0, x1, y1)).save(out, format="PNG")
        return out.getvalue()
