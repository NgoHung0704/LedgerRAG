"""Boilerplate (running header / footer / page-number) detection.

Pure and deterministic so it can be unit-tested and run on demand. The proven,
high-precision signal (Dedoc `need_header_footer_analysis`, unstructured,
docling) is verbatim REPETITION across pages at a consistent TOP or BOTTOM
position — a unique line is never flagged, and body content (whose vertical
midpoint sits in the middle of the page) is never touched.

Safety: only TEXT elements are considered by callers; table numbers are never
touched. Nothing here deletes anything — it returns candidates for a human to
review and confirm.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class BoilerElement:
    id: str
    page: int
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    text: str


@dataclass(frozen=True)
class Candidate:
    element_id: str
    page: int
    reason: str
    text: str


_WS = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")
# a page number, alone or lightly decorated: "12", "Page 12", "12 / 340", "- 12 -"
_PAGE_NUMBER = re.compile(
    r"^(?:page\s*)?\d+(?:\s*/\s*\d+)?$|^[-–—]\s*\d+\s*[-–—]$", re.IGNORECASE)

BAND = 0.15         # a header/footer's midpoint sits in the top/bottom 15%
_MIN_BAND_SHARE = 0.6
_PREVIEW = 90


def _norm_key(text: str) -> str:
    # mask digit runs so a running header with a changing page number groups
    # together across pages ("Chapter 3 · 12" and "Chapter 3 · 13")
    return _DIGITS.sub("#", _WS.sub(" ", text.strip().lower()))


def _preview(text: str) -> str:
    t = _WS.sub(" ", text.strip())
    return t if len(t) <= _PREVIEW else t[:_PREVIEW] + "…"


def detect_boilerplate(elements: list[BoilerElement]) -> list[Candidate]:
    """Running headers/footers and page numbers among the given TEXT elements.

    A group repeating on >= max(2, ceil(0.5 * n_pages)) distinct pages, with its
    occurrences predominantly in the top or bottom band, is flagged. Page-number
    patterns at a margin are flagged independently. Deduped, ordered by page."""
    texts = [e for e in elements if e.text and e.text.strip()]
    if not texts:
        return []
    pages = sorted({e.page for e in texts})
    threshold = max(2, math.ceil(0.5 * len(pages)))

    # document-wide vertical extent -> top/bottom bands. Global (not per-page)
    # so a sparse page still measures its lines against the real page height,
    # and it works regardless of the bbox coordinate convention. A header/footer
    # sits near the global top/bottom; body content sits in the middle.
    top = min(e.bbox[1] for e in texts)
    bot = max(e.bbox[3] for e in texts)
    height = bot - top

    def band(e: BoilerElement) -> str | None:
        if height <= 0:
            return "edge"
        mid = (e.bbox[1] + e.bbox[3]) / 2
        if mid <= top + BAND * height:
            return "header"
        if mid >= bot - BAND * height:
            return "footer"
        return None  # body content — never boilerplate

    found: dict[str, Candidate] = {}

    # 1) repetition across pages at a consistent margin (the primary signal)
    groups: dict[str, list[BoilerElement]] = defaultdict(list)
    for e in texts:
        groups[_norm_key(e.text)].append(e)
    for key, group in groups.items():
        if not key:
            continue
        distinct_pages = {e.page for e in group}
        if len(distinct_pages) < threshold:
            continue
        bands = [band(e) for e in group]
        headers = bands.count("header")
        footers = bands.count("footer")
        placed = headers + footers + bands.count("edge")
        if placed < _MIN_BAND_SHARE * len(group):
            continue  # mostly mid-page -> repeated body content, leave it
        label = "header" if headers >= footers else "footer"
        for e in group:
            found[e.id] = Candidate(
                e.id, e.page,
                f"repeated on {len(distinct_pages)} pages · {label}",
                _preview(e.text))

    # 2) page numbers at a margin (independent of repetition)
    for e in texts:
        if e.id in found:
            continue
        stripped = e.text.strip()
        if len(stripped) <= 16 and _PAGE_NUMBER.match(stripped) and band(e):
            found[e.id] = Candidate(e.id, e.page, "page number", _preview(e.text))

    return sorted(found.values(), key=lambda c: (c.page, str(c.element_id)))
