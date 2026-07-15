"""Cross-page table merging (text-layer PDFs): a table ending at the bottom
of page N continuing at the top of page N+1 becomes ONE logical table —
grids concatenated (repeated header dropped), crops stitched, parsed once."""

import io

import fitz
from PIL import Image

from tablerag.ingestion.imaging import stitch_vertical
from tablerag.ingestion.layout import (
    PageLayout,
    Region,
    analyze_document,
    merge_cross_page_tables,
    merge_grids,
)


def _png(w=100, h=50, color="white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------- pure helpers

def test_merge_grids_drops_repeated_header():
    top = [["Domaine", "Technique"], ["Fabrication", "Chaudronnerie"]]
    bottom = [["Domaine", "Technique"], ["Maintenance", "Mécanique"]]
    merged = merge_grids(top, bottom)
    assert len(merged) == 3  # header of the continuation dropped
    assert merged[-1] == ["Maintenance", "Mécanique"]


def test_merge_grids_keeps_different_first_row():
    top = [["Domaine", "Technique"], ["Fabrication", "Chaudronnerie"]]
    bottom = [["Maintenance", "Mécanique"]]
    assert len(merge_grids(top, bottom)) == 3


def test_merge_grids_heals_seam_leading_prefix():
    """Glossaire case: the continuation page doesn't reprint 'Fabrication'
    (col 0) nor 'Production sidérurgique' (col 1) for the group cut mid-way."""
    top = [
        ["Domaine", "Famille", "Technique", "Activités"],
        ["Fabrication", "Assemblage/Montage", "Mécanique", "Vissage"],
        [None, "Production sidérurgique", "Fusion", "Chargement-addition"],
    ]
    bottom = [
        [None, None, "Coulée Laminage", "Affinage"],          # cut group
        [None, "Transformation des métaux", "Matriçage", "Montage"],
        ["Maintenance", "Mécanique", "Diagnostic", "Dépannage"],
    ]
    merged = merge_grids(top, bottom)
    seam_row = merged[3]
    assert seam_row[0] == "Fabrication"               # carried across the seam
    assert seam_row[1] == "Production sidérurgique"   # carried across the seam
    # next row: col 1 speaks for itself, col 0 still carried
    assert merged[4][0] == "Fabrication"
    assert merged[4][1] == "Transformation des métaux"
    # once a column gets its own value, the carry stops
    assert merged[5][0] == "Maintenance"


def test_merge_grids_seam_never_carries_numbers_or_right_side_blanks():
    top = [["Poste", "T1", "Emploi"],
           ["Salaires", "812400", "Directeur"]]
    bottom = [[None, None, None],            # fully blank row
              ["Interim", "96200", None]]    # blank on the RIGHT of content
    merged = merge_grids(top, bottom)
    # col 0 label carried on the fully-blank seam row...
    assert merged[2][0] == "Salaires"
    # ...but the numeric column is NEVER duplicated across pages
    assert merged[2][1] in (None, "")
    # and a blank sitting right of content is untouched (genuinely empty)
    assert merged[3][2] in (None, "")


def test_stitch_vertical_stacks_and_pads():
    out = stitch_vertical(_png(100, 50), _png(80, 30))
    with Image.open(io.BytesIO(out)) as img:
        assert img.width == 100
        assert img.height == 80


def test_stitch_vertical_bad_bytes_failsafe():
    good = _png()
    assert stitch_vertical(good, b"junk") == good


# ------------------------------------------------------------- merge logic

def _page(page_no: int, regions: list[Region], is_scan=False) -> PageLayout:
    return PageLayout(page=page_no, width=595, height=842,
                      image_png=_png(), is_scan=is_scan, regions=regions)


def _table(y0: float, y1: float, grid=None, x0=50.0, x1=545.0) -> Region:
    return Region(type="table", bbox=(x0, y0, x1, y1),
                  grid=grid or [["h1", "h2"], ["a", "1"]], crop_png=_png())


def test_two_page_table_is_merged():
    pages = [
        _page(1, [_table(400, 800)]),           # ends at 800/842 = 95% ✓
        _page(2, [_table(40, 300)]),            # starts at 40/842 = 5% ✓
    ]
    merge_cross_page_tables(pages)
    tables_p1 = [r for r in pages[0].regions if r.type == "table"]
    tables_p2 = [r for r in pages[1].regions if r.type == "table"]
    assert len(tables_p1) == 1 and len(tables_p2) == 0
    assert tables_p1[0].span_pages == [2]
    assert len(tables_p1[0].grid) == 3  # 2 + 2 minus repeated header


def test_three_page_chain_merges_into_first():
    pages = [
        _page(1, [_table(400, 800)]),
        _page(2, [_table(40, 800)]),   # continuation that itself continues
        _page(3, [_table(40, 300)]),
    ]
    merge_cross_page_tables(pages)
    assert [len([r for r in p.regions if r.type == "table"]) for p in pages] \
        == [1, 0, 0]
    assert pages[0].regions[0].span_pages == [2, 3]


def test_no_merge_when_table_does_not_reach_bottom():
    pages = [_page(1, [_table(100, 400)]),      # ends mid-page
             _page(2, [_table(40, 300)])]
    merge_cross_page_tables(pages)
    assert len(pages[1].regions) == 1


def test_no_merge_when_continuation_starts_low():
    pages = [_page(1, [_table(400, 800)]),
             _page(2, [_table(300, 500)])]      # starts mid-page: a new table
    merge_cross_page_tables(pages)
    assert len(pages[1].regions) == 1


def test_no_merge_when_columns_differ():
    pages = [
        _page(1, [_table(400, 800, grid=[["a", "b", "c"], ["1", "2", "3"]])]),
        _page(2, [_table(40, 300, grid=[["x", "y"], ["1", "2"]])]),
    ]
    merge_cross_page_tables(pages)
    assert len(pages[1].regions) == 1


def test_no_merge_when_x_footprints_disjoint():
    pages = [_page(1, [_table(400, 800, x0=50, x1=250)]),
             _page(2, [_table(40, 300, x0=350, x1=545)])]
    merge_cross_page_tables(pages)
    assert len(pages[1].regions) == 1


def test_scan_pages_not_merged():
    pages = [_page(1, [_table(400, 800)], is_scan=True),
             _page(2, [_table(40, 300)], is_scan=True)]
    merge_cross_page_tables(pages)
    assert len(pages[1].regions) == 1


# ------------------------------------------------------------- integration

def _draw_table(page, x0, y0, n_rows, n_cols, cw=90, ch=22, prefix="r"):
    for i in range(n_rows + 1):
        page.draw_line((x0, y0 + i * ch), (x0 + n_cols * cw, y0 + i * ch))
    for j in range(n_cols + 1):
        page.draw_line((x0 + j * cw, y0), (x0 + j * cw, y0 + n_rows * ch))
    for r in range(n_rows):
        for c in range(n_cols):
            page.insert_text((x0 + c * cw + 6, y0 + r * ch + 15),
                             f"{prefix}{r}c{c}", fontsize=9)


def test_real_pdf_cross_page_table_merged():
    doc = fitz.open()
    p1 = doc.new_page()  # 595x842
    p1.insert_text((50, 40), "Un paragraphe avant le grand tableau.")
    _draw_table(p1, 50, 700, n_rows=6, n_cols=3)          # ends at y=832 (99%)
    p2 = doc.new_page()
    _draw_table(p2, 50, 40, n_rows=4, n_cols=3, prefix="s")  # starts at 5%
    p2.insert_text((50, 200), "Texte après la fin du tableau.")

    pages = analyze_document(doc.tobytes(), dpi=100, min_chars=8, table_dpi=100)
    p1_tables = [r for r in pages[0].regions if r.type == "table"]
    p2_tables = [r for r in pages[1].regions if r.type == "table"]
    assert len(p1_tables) == 1
    assert len(p2_tables) == 0, "continuation fragment must be absorbed"
    merged = p1_tables[0]
    assert merged.span_pages == [2]
    assert len(merged.grid) == 10  # 6 + 4 rows, headers differ so none dropped
    # the stitched crop is taller than a single fragment
    with Image.open(io.BytesIO(merged.crop_png)) as img:
        assert img.height > 300
