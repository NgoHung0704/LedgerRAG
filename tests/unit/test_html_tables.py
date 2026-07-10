"""Deterministic rowspan-collapse for display HTML (CETIAT merged-cell look)."""

import re

from tablerag.ingestion.html_tables import collapse_vertical_merges


def _cells(html):
    return re.findall(r"<t[dh][^>]*>.*?</t[dh]>", html)


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


def test_malformed_html_returns_original():
    junk = "not <table html at all"
    assert collapse_vertical_merges(junk) == junk


def test_none_and_empty_pass_through():
    assert collapse_vertical_merges(None) is None
    assert collapse_vertical_merges("") == ""
