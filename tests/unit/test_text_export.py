"""The parse export.

Its whole purpose is that nothing is left out: someone reads it to find out
why a document parsed badly, and a tidy summary of a bad parse is evidence of
nothing. So these tests are about completeness and about the chunks being
shown verbatim.
"""

import json

from tablerag.core.text_export import render

DOC = {"filename": "Notice.pdf", "status": "done", "page_count": 3,
       "error": None}


def element(**kw) -> dict:
    base = dict(page=1, type="text", bbox=[10, 20, 110, 70], confidence=1.0,
                needs_review=False, context=None, caption=None,
                description=None, palette=None, chart_check=None,
                parse_error=None, span_pages=None, unusable=False,
                edited=False, ocr=False, layout_suspect=False,
                decorative=False, chunks=[], table=None)
    return {**base, **kw}


def test_chunks_are_shown_verbatim_because_they_are_what_is_matched():
    """Retrieval matches the chunk text and nothing else. Paraphrasing it here
    would hide the very thing being diagnosed."""
    text = "Ligne une\n\nLigne deux — avec des « guillemets » et 27,6 %"
    out = render(DOC, [element(chunks=[text])])
    assert text in out
    assert "indexed text (1 chunk)" in out


def test_a_table_shows_html_records_and_summary_raw():
    table = {"html": "<table><tr><td>Cadres</td></tr></table>",
             "summary": "effectifs", "n_rows": 2, "n_cols": 2,
             "parse_strategy": "vlm",
             "records": [{"dimensions": {"c": "Cadres"},
                          "metrics": {"n": 120}, "raw_values": {"n": "120"}}]}
    out = render(DOC, [element(type="table", table=table)])
    assert "<table><tr><td>Cadres</td></tr></table>" in out   # not escaped
    assert json.dumps({"c": "Cadres"}, ensure_ascii=False)[1:-1] in out
    assert "html (2x2, vlm)" in out and "summary (routing)" in out


def test_a_figure_shows_what_made_it_findable():
    """The heading and the palette are the anchors, and they are invisible
    anywhere else — the point of the export is to see them."""
    out = render(DOC, [element(
        type="figure", page=9, context="DEFINITIONS DES VERRES :",
        description="Grille de classification des verres.",
        palette=[{"name": "turquoise", "hex": "#6d9cb0", "share": 0.32}],
        chunks=["DEFINITIONS DES VERRES :\n\nGrille…"])])
    assert "heading above: DEFINITIONS DES VERRES :" in out
    assert "turquoise (#6d9cb0, 32%)" in out
    assert "description (parser model, not text from the page)" in out


def test_every_flag_that_changed_a_decision_is_printed():
    out = render(DOC, [element(needs_review=True, unusable=True, edited=True,
                               decorative=True, layout_suspect=True, ocr=True,
                               span_pages=[3, 4], parse_error="contract")])
    for expected in ("NEEDS REVIEW", "unusable", "edited by hand", "decorative",
                     "column layout", "OCR", "spans pages 3, 4",
                     "parse error: contract"):
        assert expected in out, expected


def test_an_element_that_reached_no_index_says_so():
    """The failure that looks like nothing: an element exists, has a crop, and
    contributes not one searchable word."""
    out = render(DOC, [element(type="figure", chunks=[])])
    assert "(nothing indexed)" in out


def test_pages_are_headed_in_order():
    out = render(DOC, [element(page=1), element(page=3), element(page=3)])
    assert out.index("PAGE 1") < out.index("PAGE 3")
    assert out.count("PAGE 3") == 1        # one heading, not one per element


def test_the_header_counts_what_is_there():
    out = render(DOC, [element(type="text"), element(type="table"),
                       element(type="figure"), element(type="figure")])
    assert "4 elements (2 figure, 1 table, 1 text)" in out
