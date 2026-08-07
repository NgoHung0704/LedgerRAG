"""Promoting text back to a table — the missing half of convert-to-text.

A page laid out as a grid extracts as flattened prose. The VLM re-read turns it
back into a markdown table, but that markdown could only be saved as TEXT, so a
table the reviewer had just recovered stayed unsearchable as a table: no
records, no routing summary.
"""

import pytest

from tablerag.core.table_text import markdown_table_to_grid


def test_only_the_pipe_lines_are_read():
    """A re-read gives a heading, a table and a closing sentence. Someone
    pressing "this is a table" is asking for the table."""
    grid = markdown_table_to_grid(
        "Voici le tableau de garantie.\n\n"
        "| Soins | Socle |\n"
        "|-------|-------|\n"
        "| Inlays-onlays | 300 %BRSS |\n"
        "| Prothèses dentaires | 430 %BRSS |\n\n"
        "Les remboursements interviennent en complément.")
    assert grid == [["Soins", "Socle"],
                    ["Inlays-onlays", "300 %BRSS"],
                    ["Prothèses dentaires", "430 %BRSS"]]


def test_the_rule_under_the_header_is_not_a_row():
    grid = markdown_table_to_grid("| a | b |\n| :--- | ---: |\n| 1 | 2 |")
    assert grid == [["a", "b"], ["1", "2"]]


def test_a_short_row_is_padded_rather_than_lost():
    """A hand-written table often omits the trailing empty cells, and dropping
    the row would drop a fact."""
    assert markdown_table_to_grid("| a | b | c |\n|---|---|---|\n| 1 |") == [
        ["a", "b", "c"], ["1", "", ""]]


@pytest.mark.parametrize("text", [
    "Rien qu'une phrase.",
    "| une seule ligne |",           # a header with nothing under it
    "",
])
def test_prose_is_not_a_table(text):
    assert markdown_table_to_grid(text) is None


def test_a_converted_table_yields_the_same_records_as_a_detected_one():
    """A table made here must be indexed exactly like one found at ingest —
    otherwise the reviewer recovers a table that answers differently from an
    identical one the parser found."""
    from tablerag.ingestion.table_pipeline import records_from_grid

    grid = markdown_table_to_grid(
        "| Soins | Socle |\n|---|---|\n| Inlays-onlays | 300 %BRSS |")
    record = records_from_grid(grid, "fr")[0]
    assert record["dimensions"] == {"soins": "Inlays-onlays"}
    assert record["metrics"] == {"socle": 300.0}
    assert record["raw_values"] == {"socle": "300 %BRSS"}
