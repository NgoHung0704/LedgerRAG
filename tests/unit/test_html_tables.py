"""Deterministic rowspan-collapse for display HTML (CETIAT merged-cell look)."""

import re

from tablerag.ingestion.html_tables import collapse_vertical_merges, html_to_text


def _cells(html):
    return re.findall(r"<t[dh][^>]*>.*?</t[dh]>", html)


def test_html_to_text_flattens_cells_for_indexing():
    html = ("<table><tr><th>Domaine</th><th>Techniques</th></tr>"
            "<tr><td>Chaudronnerie</td><td>Tuyauterie<br>Soudure</td></tr>"
            "</table>")
    text = html_to_text(html)
    for token in ("Domaine", "Chaudronnerie", "Tuyauterie", "Soudure"):
        assert token in text
    assert "<" not in text and ">" not in text  # tags gone


def test_html_to_text_unescapes_entities():
    assert html_to_text("<td>52&nbsp;&agrave;&nbsp;54</td>") == "52 à 54"


def test_html_to_text_empty_is_blank():
    assert html_to_text(None) == ""
    assert html_to_text("") == ""


def test_collapses_repeated_group_labels_into_rowspan():
    html = (
        "<table>"
        "<tr><td>15</td><td>H</td></tr>"
        "<tr><td>16</td><td>H</td></tr>"
        "<tr><td>17</td><td>I</td></tr>"
        "<tr><td>18</td><td>I</td></tr>"
        "</table>")
    out = collapse_vertical_merges(html)
    assert '<td rowspan="2">H</td>' in out
    assert '<td rowspan="2">I</td>' in out
    # the classe column (all distinct) is untouched
    for classe in ("15", "16", "17", "18"):
        assert f"<td>{classe}</td>" in out
    # H and I each appear once now (merged), not twice
    assert out.count(">H<") == 1
    assert out.count(">I<") == 1


def test_already_merged_is_idempotent():
    html = ('<table><tr><td>15</td><td rowspan="2">H</td></tr>'
            "<tr><td>16</td></tr></table>")
    out = collapse_vertical_merges(html)
    assert out.count(">H<") == 1
    assert 'rowspan="2"' in out


def test_empty_cells_are_not_merged():
    html = ("<table>"
            "<tr><td>a</td><td>H</td><td>Directeur</td></tr>"
            "<tr><td>b</td><td>H</td><td></td></tr>"
            "</table>")
    out = collapse_vertical_merges(html)
    assert '<td rowspan="2">H</td>' in out
    # the empty Emplois cells stay separate (no rowspan on an empty cell)
    assert 'rowspan="2"></td>' not in out.replace(" ", "")


def test_headers_are_not_merged():
    html = ("<table>"
            "<tr><th>Groupe</th><td>x</td></tr>"
            "<tr><th>Groupe</th><td>y</td></tr>"
            "</table>")
    out = collapse_vertical_merges(html)
    # two <th>Groupe</th> remain (headers never collapsed)
    assert out.count("Groupe") == 2


def test_distinct_values_untouched():
    html = "<table><tr><td>1</td></tr><tr><td>2</td></tr></table>"
    out = collapse_vertical_merges(html)
    assert "rowspan" not in out


def test_interior_blank_run_merges_into_left_label_as_colspan():
    """Glossaire: Maintenance rows have Techniques as ONE wide cell in the
    original; the grid turned it into [label, blank] -> re-merge as colspan."""
    html = (
        "<table>"
        "<tr><th>Domaine</th><th>Famille</th><th>Sous</th><th>Activités</th></tr>"
        "<tr><td>Fabrication</td><td>Chaudronnerie</td><td>Tuyauterie</td><td>Assemblage</td></tr>"
        "<tr><td>Maintenance</td><td>Mécanique Electrotechnique</td><td></td><td>Diagnostic</td></tr>"
        "</table>")
    out = collapse_vertical_merges(html)
    assert '<td colspan="2">Mécanique Electrotechnique</td>' in out
    # the Fabrication row keeps its two separate technique cells
    assert "<td>Chaudronnerie</td>" in out and "<td>Tuyauterie</td>" in out


def test_numeric_columns_keep_their_missing_blanks():
    html = (
        "<table>"
        "<tr><th>Poste</th><th>T1</th><th>T2</th></tr>"
        "<tr><td>Salaires</td><td>812400</td><td>824100</td></tr>"
        "<tr><td>Formation</td><td></td><td>15800</td></tr>"
        "</table>")
    out = collapse_vertical_merges(html)
    # the missing T1 value must NOT be swallowed into a colspan
    assert "colspan" not in out


def test_trailing_blanks_never_merged():
    html = ("<table>"
            "<tr><th>A</th><th>B</th><th>C</th></tr>"
            "<tr><td>lbl</td><td>x</td><td>y</td></tr>"
            "<tr><td>lbl2</td><td>x2</td><td></td></tr>"
            "</table>")
    out = collapse_vertical_merges(html)
    assert "colspan" not in out


def test_blank_header_th_merges_into_left_label_header():
    """Glossaire header: 'Techniques' spans family+sub columns; the blank th
    must merge as colspan so the header aligns with the data rows."""
    html = (
        "<table>"
        "<tr><th>Domaines</th><th>Techniques</th><th></th><th>Activités</th></tr>"
        "<tr><td>Fabrication</td><td>Chaudronnerie</td><td>Tuyauterie</td><td>Assemblage</td></tr>"
        "</table>")
    out = collapse_vertical_merges(html)
    assert '<th colspan="2">Techniques</th>' in out


def test_trailing_blank_header_over_data_column_not_merged():
    """CETIAT-style: the salary column has an EMPTY header — it must stay its
    own (trailing) cell, never swallowed into 'Classe d'emploi'."""
    html = (
        "<table>"
        "<tr><th>Groupe</th><th>Classe</th><th></th></tr>"
        "<tr><td>A</td><td>1</td><td>21 700</td></tr>"
        "</table>")
    out = collapse_vertical_merges(html)
    assert "colspan" not in out


def test_in_cell_line_breaks_preserved():
    html = ("<table><tr><th>Techniques</th></tr>"
            "<tr><td>Comptabilité<br>Contrôle de gestion<br>Finances<br>Audit</td></tr>"
            "</table>")
    out = collapse_vertical_merges(html)
    assert "Comptabilité<br>Contrôle de gestion<br>Finances<br>Audit" in out


def test_multiline_cells_still_merge_vertically():
    html = ("<table><tr><th>T</th></tr>"
            "<tr><td>A<br>B</td></tr>"
            "<tr><td>A<br>B</td></tr></table>")
    out = collapse_vertical_merges(html)
    assert '<td rowspan="2">A<br>B</td>' in out


def test_malformed_html_returns_original():
    junk = "not <table html at all"
    assert collapse_vertical_merges(junk) == junk


def test_none_and_empty_pass_through():
    assert collapse_vertical_merges(None) is None
    assert collapse_vertical_merges("") == ""
