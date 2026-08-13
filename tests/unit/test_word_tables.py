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


def _prose_line(y: float, x0: float, x1: float, word: str, seed: int = 0) -> list[tuple]:
    """A line of running text: word widths that wander, spaces too small to cut.

    A 4pt space is under _COLUMN_GAP, so a line like this is ONE cell — which is
    what stops a paragraph being read as a row, and why the widths must differ
    line to line the way real words do."""
    widths = [30.0, 18.0, 44.0, 25.0, 37.0, 21.0]
    words, x, i = [], x0, seed
    while x + widths[i % len(widths)] <= x1:
        words.append(_w(x, y, word, widths[i % len(widths)]))
        x += widths[i % len(widths)] + 4.0
        i += 1
    return words


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


# --- the two failures seen on a REAL page ----------------------------------
# EPSENS FLEXI TAUX COURT ISR SOLIDAIRE p2 is set in two columns: risk table on
# the left, market commentary on the right. Both defects below were dumped from
# it, not imagined.

# left column: heading, a paragraph, the risk table, more paragraph
RISK_TABLE = [
    [_w(22.0, 120.0, "Indicateurs", 120.0), _w(160.0, 120.0, "1 an"),
     _w(200.0, 120.0, "3 ans"), _w(240.0, 120.0, "5 ans")],
    [_w(22.0, 132.0, "Volatilite", 120.0), _w(160.0, 132.0, "8,12"),
     _w(200.0, 132.0, "9,44"), _w(240.0, 132.0, "10,32")],
    [_w(22.0, 144.0, "Tracking", 120.0), _w(160.0, 144.0, "0,12"),
     _w(200.0, 144.0, "0,36"), _w(240.0, 144.0, "0,32")],
]
LEFT_COLUMN = (_prose_line(54.0, 22.0, 266.0, "Risque", 1)
               + [w for i, y in enumerate((66.0, 78.0, 90.0, 102.0))
                  for w in _prose_line(y, 22.0, 266.0, "gestion", i)]
               + [w for row in RISK_TABLE for w in row]
               + [w for i, y in enumerate((174.0, 186.0, 198.0, 210.0,
                                           222.0, 234.0, 246.0, 258.0))
                  for w in _prose_line(y, 22.0, 266.0, "gestion", i + 5)])
# right column: 20 lines of commentary on a 12pt grid. Three of them fall on the
# table's baselines - not by design, by the arithmetic of two columns set on the
# same page, and that is exactly how the dump came out:
#   ['Tracking error (en %)', '0,12', '0,36', '0,32',
#    'annuel autour de 1%. La banque centrale']
COMMENTARY = [w for i in range(20)
              for w in _prose_line(60.0 + 12.0 * i, 310.0, 586.0, "commentaire", i)]


def test_the_commentary_beside_a_table_does_not_become_a_column_of_it():
    found = find_word_tables(LEFT_COLUMN + COMMENTARY)
    assert len(found) == 1, "the commentary column must not be a second table"
    bbox, grid = found[0]
    assert bbox[2] <= 300.0, "the region must stop at the gutter, not cross it"
    assert not any("commentaire" in cell for row in grid for cell in row), \
        "a sentence printed beside a row is not a cell of that row"
    assert len(grid[0]) == 4, "four columns, not five"
    assert grid[2][grid[0].index("3 ans")] == "0,36"


def test_justified_prose_whose_gaps_line_up_is_not_a_table():
    # justification stretches spaces to reach the margin, so two unlucky lines
    # align on nothing but accident. They carry no figure, and a table in these
    # documents is a table OF something measured.
    a = [_w(416.0, 681.0, "orientation", 70.0), _w(500.0, 681.0, "avec", 28.0),
         _w(545.0, 681.0, "des", 22.0)]
    b = [_w(416.0, 693.0, "niveaux", 60.0), _w(498.0, 693.0, "de", 30.0),
         _w(543.0, 693.0, "taux", 20.0)]
    assert edges_align(split_cells(a), split_cells(b)), \
        "these really do align - alignment alone cannot be the whole test"
    assert find_word_tables(a + b) == []


def test_a_table_alone_in_its_column_is_not_shredded_into_one_band_per_column():
    # nothing else in the left column, so the table's OWN inter-column gaps are
    # empty all the way down the page and are crossed by only three lines out of
    # twenty-three. Measured against the page they look like gutters and the
    # table is cut into four one-cell strips - it disappears entirely. Measured
    # against the smaller side they are crossed by three lines out of three.
    found = find_word_tables([w for row in RISK_TABLE for w in row] + COMMENTARY)
    assert found, "the risk table must survive being beside a column of prose"
    grid = found[0][1]
    # asserting only that the header and the value agree is not enough: cut at
    # its widest gap the table loses its LABEL column and the three figure
    # columns still line up perfectly with each other. 0,36 under "3 ans" of
    # nothing at all is not an answer.
    assert grid[2][0] == "Tracking", "the figures must keep the label they belong to"
    assert grid[0].index("3 ans") == grid[2].index("0,36")
    # ...and it must not have swallowed the commentary either. Surviving is half
    # the requirement; this fixture is flexi-p2, where the left column holds
    # NOTHING but the table, so most of its lines merge with a prose line and
    # the gutter has to be found from a handful of rows against forty.
    assert not any("commentaire" in cell for row in grid for cell in row), \
        f"the commentary is not part of the risk table: {grid[0]}"


# --- columns closer together than the words inside one label ----------------
# rhone-p1 LES PRINCIPALES LIGNES, transcribed from `make eval-detection
# ARGS="--dump --lines"`:
#     y= 653.5 cells= 2 ['Valeurs action', 'Poids Secteur']
#     y= 666.6 cells= 2 ['ADOCIA',         '1,52% Santé']
# Poids and Secteur are separated by LESS space than the two words of "Valeurs
# actions" are. No gap threshold cuts this line correctly - lower it and the
# label splits, keep it and the two columns fuse - which is why 1,52% could not
# be reached on four of the six documents.
LIGNES = [
    [_w(22.0, 654.0, "Valeurs", 30.0), _w(58.0, 654.0, "actions", 28.0),
     _w(200.0, 654.0, "Poids", 24.0), _w(228.0, 654.0, "Secteur", 30.0)],
    [_w(22.0, 666.0, "ADOCIA", 36.0), _w(200.0, 666.0, "1,52%", 24.0),
     _w(228.0, 666.0, "Sante", 26.0)],
    [_w(22.0, 678.0, "ARTPRICE", 60.0), _w(200.0, 678.0, "0,74%", 24.0),
     _w(228.0, 678.0, "Consommation", 62.0)],
    [_w(22.0, 690.0, "TOTAL", 34.0), _w(200.0, 690.0, "3,10%", 24.0),
     _w(228.0, 690.0, "Energie", 32.0)],
]


def test_columns_closer_than_a_word_gap_are_found_by_what_repeats():
    found = find_word_tables([w for row in LIGNES for w in row])
    assert len(found) == 1, "the three-column holdings table must be found"
    _, grid = found[0]
    assert grid[1] == ["ADOCIA", "1,52%", "Sante"], (
        "the weight and the sector are different columns - only the fact that "
        f"Sante, Consommation and Secteur share an x says so; got {grid[1]}")
    assert grid[0][0] == "Valeurs actions", "the label is one cell, not two"


def test_a_label_and_a_value_are_not_a_table():
    # the floor moved off the LINE and onto the COLUMNS, so something has to
    # hold it there.
    #
    # This test used to assert that THREE such pairs are refused too, on my
    # guess that filing every fiche d'identite would bury the real tables. The
    # gate then found climat-p1 reporting a single period, which makes its
    # Performances cumulees genuinely two columns and three rows - so the guess
    # was costing a real table. Two lines is where the line sits now: that is
    # what an accidental alignment looks like, and a run of three is not.
    pairs = [[_w(22.0, y, "Date", 30.0), _w(200.0, y, value, 40.0)]
             for y, value in ((300.0, "01/01/2015"), (312.0, "12,34"))]
    assert find_word_tables([w for row in pairs for w in row]) == []


def test_a_full_width_heading_does_not_weld_the_two_columns_together():
    # flexi-p1 dumped "page splits into 1 band(s)" and its rows came back
    # interleaved with the fiche d'identite printed beside them:
    #     y= 498.7 cells= 1 ['Frequence de v']
    #     y= 503.5 cells= 5 ['Performances a', '1 an', ...]
    #     y= 506.7 cells= 1 ['Quotidienne']
    # A run needs consecutive lines, so every foreign line between two rows cuts
    # the table in half. The gutter is there - a section title spanning the page
    # ("PERFORMANCES DU FONDS") is the only thing crossing it, and demanding a
    # strip that is empty over the WHOLE page height gives one line the power to
    # weld two columns together for good.
    heading = [_w(x, 40.0, "PERFORMANCES", 90.0) for x in (22.0, 130.0, 240.0,
                                                           350.0, 460.0)]
    found = find_word_tables(heading + LEFT_COLUMN + COMMENTARY)
    tables = [(b, g) for b, g in found if any("0,36" in c for r in g for c in r)]
    assert len(tables) == 1, "the risk table must still be found under a heading"
    bbox, grid = tables[0]
    assert bbox[2] <= 300.0, "the region must stop at the gutter"
    assert not any("commentaire" in c for r in grid for c in r)


# climat-p1 prints its Performances cumulees with ONE period, so the table is
# two columns wide. Transcribed from the dump:
#     y= 472.6 cells= 2 ['Performances c', '1 mois']
#     y= 481.8 cells= 3 ['Portefeuille', '-4,31', 'Frequence de v']
#     y= 496.9 cells= 2 ['Indice de refe', '-3,29']
ONE_PERIOD = [
    [_w(22.0, 472.0, "Performances", 120.0), _w(294.0, 472.0, "1 mois", 30.0)],
    [_w(22.0, 484.0, "Portefeuille", 120.0), _w(294.0, 484.0, "-4,31", 30.0)],
    [_w(22.0, 496.0, "Indice", 120.0), _w(294.0, 496.0, "-3,29", 30.0)],
]


def test_a_table_two_columns_wide_is_still_a_table_when_it_has_rows():
    found = find_word_tables([w for row in ONE_PERIOD for w in row])
    assert len(found) == 1, "a fund reporting one period still prints a table"
    assert found[0][1][1] == ["Portefeuille", "-4,31"]


# the mirror of flexi-p2: commentary on the LEFT, table on the right. Same page,
# read from the other side, and it needs the other half of the window - without
# it the forty lines of prose are counted against the table's three rows on its
# OWN column gap, and the table is cut into one band per column.
MIRROR_TABLE = [
    [_w(330.0, 120.0, "Indicateurs", 120.0), _w(470.0, 120.0, "1 an"),
     _w(510.0, 120.0, "3 ans"), _w(550.0, 120.0, "5 ans")],
    [_w(330.0, 132.0, "Volatilite", 120.0), _w(470.0, 132.0, "8,12"),
     _w(510.0, 132.0, "9,44"), _w(550.0, 132.0, "10,32")],
    [_w(330.0, 144.0, "Tracking", 120.0), _w(470.0, 144.0, "0,12"),
     _w(510.0, 144.0, "0,36"), _w(550.0, 144.0, "0,32")],
]
LEFT_COMMENTARY = [w for i in range(20)
                   for w in _prose_line(60.0 + 12.0 * i, 22.0, 300.0,
                                        "commentaire", i)]


def test_a_table_to_the_RIGHT_of_the_prose_keeps_its_columns():
    found = find_word_tables([w for row in MIRROR_TABLE for w in row]
                             + LEFT_COMMENTARY)
    assert found, "the table must survive prose printed down its left"
    grid = found[0][1]
    assert grid[2][0] == "Tracking", "the figures must keep their label"
    assert not any("commentaire" in cell for row in grid for cell in row)
