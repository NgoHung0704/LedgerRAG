"""Multi-table detection: accept/dedup logic + a real two-table PDF page."""

import fitz

from tablerag.ingestion.layout import (
    accept_table,
    analyze_document,
    detect_tables,
    duplicates_table_text,
    grid_cell_texts,
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


# --- table text must not be indexed twice (run 6: text copy outranked it) ---

BAREME_GRID = [["Groupe d'emplois", "Classe d'emploi", ""],
               ["A", "1", "21 700"], ["A", "2", "21 850"],
               ["B", "3", "22 450"], ["C", "5", "24 250"],
               ["H", "16", "52 000"]]


def test_grid_cell_texts_normalizes_and_drops_trivia():
    cells = grid_cell_texts(BAREME_GRID)
    assert "groupe d'emplois" in cells and "21 700" in cells
    assert "" not in cells          # blank header cell dropped
    assert "1" not in cells         # single characters are not evidence


def test_block_that_is_the_table_read_as_lines_is_dropped():
    """The exact shape observed on the box: the barème as loose lines."""
    block = ("Groupe d'emplois\nClasse d'emploi\nA\n1\n21 700\n2\n21 850\n"
             "B\n3\n22 450\nC\n5\n24 250\nH\n16\n52 000")
    assert duplicates_table_text(block, grid_cell_texts(BAREME_GRID))


def test_prose_on_the_same_page_survives():
    """a14's answer lives in prose next to that table — it must be kept."""
    prose = ("A partir de 2024, le barème unique des salaires minima "
             "hiérarchiques applicable, pour une durée hebdomadaire de "
             "travail effectif de 35 heures, sur la base mensualisée de "
             "151,66 heures, est fixé comme suit :")
    assert not duplicates_table_text(prose, grid_cell_texts(BAREME_GRID))


def test_short_or_unrelated_blocks_are_never_dropped():
    cells = grid_cell_texts(BAREME_GRID)
    assert not duplicates_table_text("21 700", cells)          # too few lines
    assert not duplicates_table_text("a\nb\nc", cells)         # no overlap
    assert not duplicates_table_text("A\n1\n21 700", set())    # no tables


def _draw_borderless(page, y0: float, label_x: float = 60.0):
    """A table held together by nothing but where its words sit."""
    columns = (label_x, 300.0, 360.0, 420.0)
    for i, row in enumerate((("Indicateurs", "1 an", "3 ans", "5 ans"),
                             ("Volatilite", "8,12", "9,44", "10,32"),
                             ("Tracking", "0,12", "0,36", "0,32"))):
        for x, cell in zip(columns, row):
            page.insert_text((x, y0 + i * 14.0), cell, fontsize=9)


def test_a_borderless_table_is_found_even_when_the_page_has_a_ruled_one():
    """The gate said flexi-p2 1/2, rhone-p1 3/4, monetaire-p1 3/4 — every one of
    them a page where SOMETHING was detected and the missing table was
    borderless. The word detector ran only where the page came up completely
    empty, so on those pages it never ran at all. One ruled table on the page
    was enough to protect every borderless one from being looked for."""
    doc = fitz.open()
    page = doc.new_page()
    _draw_table(page, 50, 60, n_rows=3, n_cols=3)   # ruled: found by lines_*
    _draw_borderless(page, y0=400.0)                # borderless: words only
    found = detect_tables(page)

    flat = " ".join(str(cell or "") for _, grid in found
                    for row in grid for cell in row)
    assert "0,36" in flat, (
        f"the borderless table was not detected; {len(found)} region(s) found")
    assert "8,12" in flat and "10,32" in flat


def test_a_text_region_that_cut_through_the_numbers_is_refused():
    """vertes-p1 and flexi-p1, straight from the gate:

        #0 Table (201, 466, 399, 494) 2x3 ['3 -1,91 -1,0', '4,96 2,4', '3 18,60']
        #1 Table (304, 513, 399, 541) 2x2 [',79 3,89', '4,68']

    A cell beginning with a comma is a value sliced in half - 4,79 became "4" in
    one cell and ",79" in the next. These are in the index today, and they also
    veto the word detector's region for the table they sit inside, because they
    were laid down first.

    This first exempted the ruled strategies, on my argument that a ruled cell
    boundary was drawn on the page and so must be believed. vertes-p1 then
    vetoed all three of its performance tables with three RULED fragments, each
    cutting a value in half - so the argument was wrong and the exemption is
    gone. The word detector keeps it, for the opposite reason: there, refusing
    would drop the only reading of the table rather than a wrong reading that is
    vetoing a right one."""
    from tablerag.ingestion.layout import accept_table, cuts_through_numbers

    mangled = [["46 -0,33 0,0", "7,42"], ["18 0,74 -0,6", "0,45"]]
    assert accept_table(R(234, 466, 399, 494), mangled, "text", []) is False
    assert accept_table(R(234, 466, 399, 494), mangled, "lines", []) is False
    assert accept_table(R(234, 466, 399, 494), mangled, "words", []) is True

    # every mangled cell the gate actually printed, and what must survive it
    for sliced in ("3 -1,91 -1,0", "1,63 0,4", "-0,82 0,8", ",79 3,89",
                   ",06 21,02", "-2,06 8,52", "0,57 4,92", "46 -0,33 0,0"):
        assert cuts_through_numbers([[sliced]]), sliced
    for whole in ("de 2,5 à 3,5", "1 234,56", "1,52% Santé", "-10,57",
                  "31/12/2020", "Volatilité 3 ans"):
        assert not cuts_through_numbers([[whole]]), whole


def test_a_RULED_region_sliced_through_its_values_is_dropped():
    """The ruled candidates never pass through accept_table - they are filtered
    inline in detect_tables - so guarding accept_table alone left vertes-p1
    exactly where it was, with three ruled fragments vetoing its three tables.

    Two values printed inside one ruled cell is what the page's own boxes did
    there, and the resulting grid says the second column holds "-0,82 0,8"."""
    doc = fitz.open()
    page = doc.new_page()
    x0, y0, cw, ch = 60.0, 100.0, 120.0, 24.0
    for i in range(3):
        page.draw_line((x0, y0 + i * ch), (x0 + 2 * cw, y0 + i * ch))
    for j in range(3):
        page.draw_line((x0 + j * cw, y0), (x0 + j * cw, y0 + 2 * ch))
    page.insert_text((x0 + 6, y0 + 16), "Annee", fontsize=9)
    page.insert_text((x0 + cw + 6, y0 + 16), "Perf", fontsize=9)
    page.insert_text((x0 + 6, y0 + ch + 16), "2020", fontsize=9)
    page.insert_text((x0 + cw + 6, y0 + ch + 16), "-0,82 0,8", fontsize=9)

    flat = " ".join(str(cell or "") for _, grid in detect_tables(page)
                    for row in grid for cell in row)
    assert "-0,82 0,8" not in flat, f"a sliced ruled row was kept: {flat!r}"
