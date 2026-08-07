"""Drawing a value that covers several rows.

A guarantee table prints "300 %BRSS" once against two kinds of care, and
collapsing that into a rowspan is what the page looks like. But it is not
always what a reader wants: a merged cell is harder to scan across, harder to
copy one row out of, and it hides how many rows a value covers.
"""

from tablerag.core.table_text import html_to_grid
from tablerag.ingestion.html_tables import collapse_vertical_merges
from tablerag.ingestion.table_pipeline import _grid_to_html

MERGED = ('<table>\n  <tr><th>Soins</th><th>Socle</th></tr>\n'
          '  <tr><td>Soins conservateurs</td><td rowspan="2">300 %BRSS</td></tr>\n'
          '  <tr><td>Inlays-onlays</td></tr>\n'
          '  <tr><td>Prothèses dentaires</td><td>430 %BRSS</td></tr>\n</table>')


def expand(html: str) -> str:
    return _grid_to_html(html_to_grid(html))


def test_splitting_a_merged_cell_gives_every_row_its_own_value():
    out = expand(MERGED)
    assert 'rowspan' not in out
    assert out.count("300 %BRSS") == 2
    assert "Inlays-onlays</td><td>300 %BRSS" in out


def test_the_round_trip_is_exact():
    """Merging again must give back what was there, or the button would be a
    slow way to damage a table."""
    assert collapse_vertical_merges(expand(MERGED)) == MERGED


def test_both_drawings_read_as_the_same_table():
    """This is what makes it display-only. The answering context reads HTML
    through html_to_grid, so if the two forms ever disagreed there, the button
    would silently change what the document says."""
    assert html_to_grid(MERGED) == html_to_grid(expand(MERGED))


def test_records_do_not_depend_on_the_drawing():
    """Records are built from a forward-filled grid, so every row already
    carries its own value whichever way the HTML is written — nothing is
    re-indexed and no answer moves."""
    from tablerag.ingestion.table_pipeline import records_from_grid

    assert (records_from_grid(html_to_grid(MERGED), "fr")
            == records_from_grid(html_to_grid(expand(MERGED)), "fr"))
