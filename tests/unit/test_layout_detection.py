"""Multi-table detection: accept/dedup logic + a real two-table PDF page."""

import fitz
import pytest

from tablerag.ingestion.layout import (
    accept_table,
    analyze_document,
    detect_tables,
    grid_fill_ratio,
)

R = fitz.Rect


def test_grid_fill_ratio():
    assert grid_fill_ratio([["a", "b"], ["c", "d"]]) == 1.0
    assert grid_fill_ratio([["a", None], [None, ""]]) == 0.25
    assert grid_fill_ratio([]) == 0.0


def test_accept_rejects_non_grid_shapes():
    grid = [["a", "b"], ["c", "d"]]
    assert accept_table(R(0, 0, 100, 100), grid, "lines", []) is True
    assert accept_table(R(0, 0, 0, 0), grid, "lines", []) is False       # empty rect
    assert accept_table(R(0, 0, 100, 100), [["a"]], "lines", []) is False  # 1 row/col
    assert accept_table(R(0, 0, 100, 100), [["a", "b"]], "lines", []) is False  # 1 row


def test_accept_dedupes_overlapping_regions():
    grid = [["a", "b"], ["c", "d"]]
    existing = [R(0, 0, 100, 100)]
    assert accept_table(R(5, 5, 95, 95), grid, "lines", existing) is False  # inside
    assert accept_table(R(200, 200, 300, 300), grid, "lines", existing) is True  # apart


def test_text_strategy_guarded_against_sparse_prose():
    dense = [["a", "b"], ["c", "d"]]
    sparse = [["intro", None], [None, None], ["", "note"]]  # prose-like
    assert accept_table(R(0, 0, 100, 100), dense, "text", []) is True
    assert accept_table(R(0, 0, 100, 100), sparse, "text", []) is False
    # the same sparse grid IS accepted from a line strategy (real ruled table)
    assert accept_table(R(0, 0, 100, 100), sparse, "lines", []) is True


def _draw_table(page, x0, y0, n_rows, n_cols, cw=70, ch=22):
    for i in range(n_rows + 1):
        y = y0 + i * ch
        page.draw_line((x0, y), (x0 + n_cols * cw, y))
    for j in range(n_cols + 1):
        x = x0 + j * cw
        page.draw_line((x, y0), (x, y0 + n_rows * ch))
    for r in range(n_rows):
        for c in range(n_cols):
            page.insert_text((x0 + c * cw + 6, y0 + r * ch + 15), f"r{r}c{c}",
                             fontsize=9)


def test_two_tables_on_one_page_both_detected():
    doc = fitz.open()
    page = doc.new_page()
    _draw_table(page, 50, 60, n_rows=3, n_cols=3)          # first grid
    page.insert_text((50, 190), "Paragraphe de séparation entre les deux barèmes.")
    _draw_table(page, 50, 230, n_rows=3, n_cols=3)          # second grid
    pdf = doc.tobytes()

    pages = analyze_document(pdf, dpi=100, min_chars=8, table_dpi=100)
    tables = [r for r in pages[0].regions if r.type == "table"]
    assert len(tables) >= 2, f"expected both tables, got {len(tables)}"


def test_diagnose_pdf_tables_reports_per_strategy():
    from tablerag.ingestion.layout import diagnose_pdf_tables

    doc = fitz.open()
    page = doc.new_page()
    _draw_table(page, 50, 60, n_rows=3, n_cols=3)
    _draw_table(page, 50, 230, n_rows=3, n_cols=3)
    report = diagnose_pdf_tables(doc.tobytes())
    assert len(report) == 1
    page_report = report[0]
    assert set(page_report["strategies"]) == {"lines_strict", "lines", "text"}
    assert page_report["kept"] and len(page_report["kept"]) >= 2
    assert "text_chars" in page_report


def test_resolve_by_quality_prefers_finer_fuller_grid():
    """Cotation regression: lines_strict returned a TRUNCATED 7x3 blob while
    `lines` found the full 19x4 grid — quality must win over strategy order."""
    from tablerag.ingestion.layout import resolve_by_quality

    truncated = (7 * 3, 247.0 * 607, 0, R(69, 134, 316, 741))   # lines_strict
    full = (19 * 4, 459.0 * 632, 1, R(68, 135, 527, 767))       # lines
    kept = resolve_by_quality([truncated, full])
    assert kept == [1]  # the full grid wins; the overlapping blob is dropped


def test_resolve_by_quality_identical_candidates_prefer_strict():
    from tablerag.ingestion.layout import resolve_by_quality

    strict = (6 * 4, 100.0, 0, R(32, 113, 571, 725))
    loose = (6 * 4, 100.0, 1, R(32, 113, 571, 725))  # Glossaire: identical
    kept = resolve_by_quality([strict, loose])
    assert kept == [0]  # exact tie -> lines_strict


def test_resolve_by_quality_keeps_disjoint_candidates():
    from tablerag.ingestion.layout import resolve_by_quality

    a = (12, 100.0, 0, R(0, 0, 100, 100))
    b = (9, 80.0, 0, R(0, 200, 100, 300))  # no overlap: both kept
    kept = resolve_by_quality([a, b])
    assert sorted(kept) == [0, 1]


def test_detect_tables_returns_empty_on_prose_page():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 500, 700),
                        "Ceci est un paragraphe de politique RH sans aucun "
                        "tableau. " * 20, fontsize=11)
    assert detect_tables(page) == []
