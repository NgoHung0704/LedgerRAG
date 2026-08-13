"""Finding a borderless table from word coordinates.

The fixtures are the real EPSENS layout, transcribed: a heading row and two
body rows whose figures share x positions, sitting under prose that does not.
Coordinates are approximate but their RELATIONSHIPS are what the algorithm
reads, and those are copied from the page.
"""

from tablerag.ingestion.word_tables import (
    edges_align,
    find_word_tables,
    group_lines,
    split_cells,
)


def _w(x0: float, y: float, text: str, width: float = 26.0) -> tuple:
    """One word box, the shape page.get_text("words") returns."""
    return (x0, y, x0 + width, y + 9.0, text, 0, 0, 0)


# Performances cumulées (en %) | 1 mois | 2021 | 1 an | 3 ans | 5 ans | 10 ans
COLUMNS = [40.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0]
HEADER = [_w(COLUMNS[0], 100.0, "Performances"), _w(COLUMNS[1], 100.0, "1 mois"),
          _w(COLUMNS[2], 100.0, "2021"), _w(COLUMNS[3], 100.0, "1 an"),
          _w(COLUMNS[4], 100.0, "3 ans"), _w(COLUMNS[5], 100.0, "5 ans"),
          _w(COLUMNS[6], 100.0, "10 ans")]
PORTEFEUILLE = [_w(COLUMNS[0], 112.0, "Portefeuille"), _w(COLUMNS[1], 112.0, "-2,58"),
                _w(COLUMNS[2], 112.0, "9,42"), _w(COLUMNS[3], 112.0, "20,17"),
                _w(COLUMNS[4], 112.0, "31,04"), _w(COLUMNS[5], 112.0, "50,46"),
                _w(COLUMNS[6], 112.0, "148,90")]
INDICE = [_w(COLUMNS[0], 124.0, "Indice"), _w(COLUMNS[1], 124.0, "-2,05"),
          _w(COLUMNS[2], 124.0, "13,62"), _w(COLUMNS[3], 124.0, "21,88"),
          _w(COLUMNS[4], 124.0, "31,33"), _w(COLUMNS[5], 124.0, "53,66"),
          _w(COLUMNS[6], 124.0, "119,97")]

# the strategy paragraph above it: word boundaries that wander line to line
PROSE = ([_w(40.0, 60.0, "EPSENS"), _w(78.0, 60.0, "D.E.F.I.S."), _w(140.0, 60.0, "est"),
          _w(168.0, 60.0, "un"), _w(196.0, 60.0, "FCPE")]
         + [_w(40.0, 72.0, "nourricier"), _w(96.0, 72.0, "du"), _w(122.0, 72.0, "Fonds"),
            _w(171.0, 72.0, "Commun"), _w(233.0, 72.0, "de")])


def test_words_on_one_baseline_become_one_line():
    lines = group_lines(HEADER + PORTEFEUILLE)
    assert len(lines) == 2
    assert [w[4] for w in lines[0]][:2] == ["Performances", "1 mois"]


def test_a_gap_wider_than_a_space_starts_a_new_cell():
    line = split_cells(PORTEFEUILLE)
    assert len(line.cells) == 7
    assert [text for _, _, text in line.cells][:2] == ["Portefeuille", "-2,58"]


def test_words_merely_spaced_apart_stay_in_one_cell():
    # "Indice de référence" is one label, not three columns
    label = [_w(40.0, 124.0, "Indice", 26.0), _w(68.0, 124.0, "de", 12.0),
             _w(82.0, 124.0, "référence", 42.0)]
    assert len(split_cells(label).cells) == 1


def test_two_rows_of_the_same_table_align():
    assert edges_align(split_cells(PORTEFEUILLE), split_cells(INDICE))


def test_prose_lines_do_not_align():
    lines = group_lines(PROSE)
    assert not edges_align(split_cells(lines[0]), split_cells(lines[1]))


def test_the_performance_table_is_found_under_the_prose():
    found = find_word_tables(PROSE + HEADER + PORTEFEUILLE + INDICE)
    assert len(found) == 1, "the paragraph must not be swallowed into the table"
    bbox, grid = found[0]
    assert len(grid) == 3
    assert bbox[1] >= 100.0, "the table must start below the paragraph"


def test_the_value_asked_for_is_in_the_column_it_is_printed_under():
    # this is the whole point: eval-funds f1 asked for 5 ans and was given
    # 31,04, the 3 ans figure, because the value was read out of page prose
    _, grid = find_word_tables(HEADER + PORTEFEUILLE + INDICE)[0]
    header, portefeuille = grid[0], grid[1]
    assert header.index("5 ans") == portefeuille.index("50,46")
    assert header.index("3 ans") == portefeuille.index("31,04")


def test_a_missing_figure_leaves_its_column_empty():
    # a blank must not shift every later value one place left, which is exactly
    # how a number ends up reported under the wrong header
    short = [_w(COLUMNS[0], 124.0, "Indice"), _w(COLUMNS[1], 124.0, "-2,05"),
             _w(COLUMNS[2], 124.0, "13,62"), _w(COLUMNS[3], 124.0, "21,88"),
             _w(COLUMNS[4], 124.0, "31,33"), _w(COLUMNS[5], 124.0, "53,66")]
    _, grid = find_word_tables(HEADER + PORTEFEUILLE + short)[0]
    assert grid[2][-1] == "", "the absent 10-year figure must leave a gap"
    assert grid[2][5] == "53,66"


def test_a_gap_in_the_MIDDLE_does_not_shift_the_values_after_it():
    # the dangerous shape. With the hole at the end, filling cells in order
    # happens to give the right answer and proves nothing; with it in the
    # middle, every figure after the hole slides one column left and each one
    # is then reported under its neighbour's header.
    holed = [_w(COLUMNS[0], 124.0, "Indice"), _w(COLUMNS[1], 124.0, "-2,05"),
             _w(COLUMNS[3], 124.0, "21,88"), _w(COLUMNS[4], 124.0, "31,33"),
             _w(COLUMNS[5], 124.0, "53,66"), _w(COLUMNS[6], 124.0, "119,97")]
    _, grid = find_word_tables(HEADER + PORTEFEUILLE + holed)[0]
    header, indice = grid[0], grid[2]
    assert indice[2] == "", "the missing 2021 figure must leave its column empty"
    assert indice[header.index("3 ans")] == "31,33"
    assert indice[header.index("10 ans")] == "119,97"


def test_a_page_of_prose_yields_no_table():
    assert find_word_tables(PROSE) == []


def test_two_stacked_tables_are_two_regions():
    # DEFIS page 1 stacks Performances cumulées, annualisées and annuelles;
    # returning them as one block is the failure that started this
    second = [[_w(COLUMNS[0], y, "Portefeuille"), _w(COLUMNS[1], y, "20,17"),
               _w(COLUMNS[2], y, "9,43"), _w(COLUMNS[3], y, "8,51")]
              for y in (200.0, 212.0)]
    words = HEADER + PORTEFEUILLE + INDICE + [w for line in second for w in line]
    found = find_word_tables(words)
    assert len(found) == 2
    assert found[0][0][3] < found[1][0][1], "regions must not overlap vertically"
