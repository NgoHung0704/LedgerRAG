"""VLM table-region detection for scanned pages (SPEC Phase 2 §1 fallback:
"use the VLM to return bboxes"). find_tables needs a text/line layer, so on
scans the parser VLM is asked where the tables are; each region is then
cropped and parsed independently (multi-table scan pages).

Coordinate conventions: Qwen-VL grounding natively uses 0-1000 integers, so
the prompt asks for that — but the parser tolerates and normalizes all three
conventions seen in the wild (0-1 fractions, 0-1000, absolute pixels) because
VLMs don't reliably follow coordinate instructions. This module is separate
from table_pipeline so the diagnostics API can import it without dragging in
the ingestion task pipeline.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

Box = tuple[float, float, float, float]  # page fractions, (x0, y0, x1, y1)

REGION_PROMPT = (
    "The attached image is a full document page. Find EVERY distinct data "
    "table (a bordered or aligned grid of rows and columns of values). Ignore "
    "body paragraphs, titles, stamps and signatures. There may be several "
    "tables separated by text — report each one separately.\n"
    "For each table give its bounding box as integers from 0 to 1000, where "
    "(0,0) is the top-left corner of the page and (1000,1000) the bottom-right "
    "(x0,y0 = table top-left, x1,y1 = table bottom-right).\n"
    'Reply with ONLY a JSON array, e.g. '
    '[{"x0":80,"y0":100,"x1":920,"y1":340},{"x0":80,"y0":550,"x1":920,"y1":710}]. '
    "If there are no tables, reply []"
)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _clamp01(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def _iou_ish(a: Box, b: Box) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    return inter / area_a if area_a else 0.0


def _extract_raw(text: str) -> list[tuple[float, float, float, float]]:
    match = _JSON_ARRAY_RE.search(text or "")
    if not match:
        return []
    try:
        items = json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    raw = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            raw.append((float(item["x0"]), float(item["y0"]),
                        float(item["x1"]), float(item["y1"])))
        except (KeyError, TypeError, ValueError):
            continue
    return raw


def parse_region_boxes(text: str, width: int | None = None,
                       height: int | None = None) -> list[Box]:
    """Extract boxes from the VLM reply and normalize to page fractions.
    Handles 0-1 fractions, the Qwen 0-1000 convention, and absolute pixels
    (when the image size is known). Validates, dedupes, sorts top-to-bottom."""
    raw = _extract_raw(text)
    if not raw:
        return []

    max_coord = max(c for box in raw for c in box)
    if max_coord <= 1.5:                      # already fractions
        sx = sy = 1.0
    elif width and height and max_coord > 1050:  # absolute pixels
        sx, sy = float(width), float(height)
    else:                                     # Qwen-style 0-1000
        sx = sy = 1000.0

    boxes: list[Box] = []
    for x0, y0, x1, y1 in raw:
        x0, x1 = sorted((_clamp01(x0 / sx), _clamp01(x1 / sx)))
        y0, y1 = sorted((_clamp01(y0 / sy), _clamp01(y1 / sy)))
        if (x1 - x0) < 0.03 or (y1 - y0) < 0.02:  # degenerate
            continue
        box = (x0, y0, x1, y1)
        if any(_iou_ish(box, kept) > 0.6 or _iou_ish(kept, box) > 0.6
               for kept in boxes):
            continue  # near-duplicate
        boxes.append(box)
    boxes.sort(key=lambda b: (b[1], b[0]))  # reading order
    return boxes


def _image_size(png: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(io.BytesIO(png)) as img:
            return img.width, img.height
    except UnidentifiedImageError:
        return None, None


async def detect_table_regions_debug(image_png: bytes) -> tuple[list[Box], str]:
    """Returns (boxes, raw model reply) — the raw reply powers diagnostics."""
    from tablerag.core.config import get_settings
    from tablerag.models.base import Msg
    from tablerag.models.registry import get_provider

    parser = get_provider("parser")
    b64 = base64.b64encode(image_png).decode()
    parts: list[str] = []
    async for token in parser.chat(
            [Msg(role="user", content=REGION_PROMPT, images=[b64])],
            stream=True, temperature=0.0,
            options={"temperature": 0.0,
                     "num_ctx": get_settings().table_parse_num_ctx}):
        parts.append(token)
    raw = "".join(parts)
    width, height = _image_size(image_png)
    boxes = parse_region_boxes(raw, width, height)
    logger.info("VLM region detection: %d box(es) parsed from a %d-char reply",
                len(boxes), len(raw))
    return boxes, raw


async def detect_table_regions(image_png: bytes) -> list[Box]:
    """Table bounding boxes (page fractions). Empty on failure -> caller falls
    back to treating the whole page as one table."""
    try:
        boxes, _ = await detect_table_regions_debug(image_png)
        return boxes
    except Exception:  # noqa: BLE001 — detection failure must not kill the page
        logger.exception("VLM table-region detection failed (non-fatal)")
        return []
