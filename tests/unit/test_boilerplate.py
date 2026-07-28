"""Boilerplate detection: running headers/footers/page numbers are flagged by
verbatim repetition across pages at a consistent margin. The load-bearing
safety property is that REPEATED BODY CONTENT (mid-page) is never flagged — so
a unique line, or a repeated section title in the body, is left alone."""

from tablerag.ingestion.boilerplate import BoilerElement, detect_boilerplate


def _el(page: int, idx: int, text: str, y0: float, y1: float) -> BoilerElement:
    return BoilerElement(id=f"{page}-{idx}", page=page,
                         bbox=(0.0, y0, 500.0, y1), text=text)


def _flagged(elements):
    return {c.element_id: c.reason for c in detect_boilerplate(elements)}


def test_running_footer_is_flagged_body_is_not():
    els = []
    for p in range(1, 5):  # 4 pages, threshold = 2
        els.append(_el(p, 0, f"Section {p} — unique body text.", 100, 700))
        els.append(_el(p, 1, "Confidential — Acme Corp", 760, 780))
    flagged = _flagged(els)
    for p in range(1, 5):
        assert f"{p}-1" in flagged and "footer" in flagged[f"{p}-1"]
        assert f"{p}-0" not in flagged  # unique body never flagged


def test_running_header_is_flagged():
    els = []
    for p in range(1, 4):
        els.append(_el(p, 0, "ACME ANNUAL REPORT 2024", 10, 30))
        els.append(_el(p, 1, f"Body of page {p}.", 100, 700))
    flagged = _flagged(els)
    assert all(f"{p}-0" in flagged and "header" in flagged[f"{p}-0"]
               for p in range(1, 4))


def test_repeated_MID_PAGE_content_is_never_flagged():
    # the same heading in the middle of the body on every page — repetition
    # alone must not flag it; only top/bottom-margin repetition counts. Each
    # page spans top→bottom so the extent is realistic.
    tops = ["alpha preamble", "beta remarks", "gamma notes", "delta preface"]
    tails = ["wombat findings", "xenon summary", "yak details", "zebra close"]
    els = []
    for i, p in enumerate(range(1, 5)):
        els.append(_el(p, 0, tops[i], 40, 90))               # unique, near top
        els.append(_el(p, 1, "Introduction", 300, 380))      # mid-page, repeated
        els.append(_el(p, 2, tails[i], 420, 760))            # unique, near bottom
    assert _flagged(els) == {}


def test_page_number_flagged_even_when_not_repeated_enough():
    # single-page doc: repetition can't fire, the page-number detector does
    els = [
        _el(1, 0, "Some body paragraph on the only page.", 100, 700),
        _el(1, 1, "Page 5", 760, 780),
    ]
    flagged = _flagged(els)
    assert flagged.get("1-1") == "page number"
    assert "1-0" not in flagged


def test_bare_page_numbers_group_across_pages():
    els = []
    for p in range(1, 5):
        els.append(_el(p, 0, f"body {p}", 100, 700))
        els.append(_el(p, 1, str(p), 760, 780))  # 1,2,3,4 -> masked to "#"
    flagged = _flagged(els)
    assert all(f"{p}-1" in flagged for p in range(1, 5))


def test_below_threshold_not_flagged():
    els = []
    for p in range(1, 7):  # 6 pages, threshold = 3
        els.append(_el(p, 0, f"body {p}", 100, 700))
    # a footer on only 2 of the 6 pages
    els.append(_el(1, 1, "draft watermark", 760, 780))
    els.append(_el(2, 1, "draft watermark", 760, 780))
    assert _flagged(els) == {}


def test_empty_input():
    assert detect_boilerplate([]) == []
