"""Find tables by where the words sit, when the page has no ruling lines.

Measured with `make eval-detection` on six real fund factsheets: PyMuPDF's
`find_tables` reaches 25 % of pages. It is not that it reads cells badly — it
cannot tell where a table STARTS and ENDS once a page holds more than one
thing. Its three strategies return either a single blob spanning the whole page
(correctly rejected, since accepting it recreates the swallowing bug) or
nothing at all. Every page that passes has one table more or less alone on it.

But these documents are laid out on a grid even without a single rule drawn:
every figure in a column shares an x position, and a row is a set of words
sharing a baseline. That is recoverable from `page.get_text("words")`, and it
is recoverable EXACTLY — no model, no weights to download, no OCR, and the
answer is a bounding box, which is what the architecture needs. An element that
cannot say where it came from cannot carry a crop image, and without the crop a
reader cannot check the answer against the page (principle #3).

The shape of the thing being looked for:

    Performances cumulées (en %)   1 mois   2021   1 an   3 ans   5 ans
    Portefeuille                    -2,58   9,42  20,17  31,04   50,46
    Indice de référence             -2,05  13,62  21,88  31,33   53,66
                        ^        ^      ^      ^      ^      ^
                        the same gaps, line after line

Two lines belong to the same table when their gaps line up. Prose does not do
that: its word boundaries wander from line to line. That is the whole test, and
it is why this needs no threshold on how "table-like" the words look.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# a gap this wide between two words is a column boundary rather than a space.
# Below it, "Indice de référence" would split into three columns.
_COLUMN_GAP = 8.0
# two words are on the same line when their vertical centres are this close
_LINE_TOLERANCE = 3.0
# how far two boundaries may sit apart and still count as the same column edge
_EDGE_TOLERANCE = 12.0
# a table has at least this many COLUMNS once they are known
_MIN_CELLS = 3
# ...but a line only needs this many cells to be worth pairing with the next
# one. Insisting on three HERE lost LES PRINCIPALES LIGNES on four of six
# documents: Poids and Secteur sit closer together than the two words of
# "Valeurs actions" on the same line, so the gap rule fuses them and every row
# reads as two cells. No threshold fixes that - lower it and the label splits,
# keep it and the columns fuse. The columns are recovered afterwards from what
# repeats down the run, and the three-column floor is applied there instead.
_MIN_RUN_CELLS = 2
# fewer rows than this is not a table, it is a heading and a line under it
_MIN_ROWS = 2
# a run only TWO columns wide needs this many rows before it counts. climat-p1
# reports a single period, so its Performances cumulees is genuinely two columns
# and three rows, and refusing every two-column run lost it. The cost is stated:
# a fiche d'identite is also label/value, and three of its lines in a row will
# now be filed as a table. That is real tabular data with a crop and a source,
# so the cost is noise in the index, not a wrong answer - and two aligned lines,
# which is what most accidents look like, are still refused.
_MIN_NARROW_ROWS = 3
# a vertical gap wider than this many times the line's own height ends the
# table. Columns alone cannot separate two STACKED tables - the second one's
# figures sit under the first one's columns by construction, which is what
# being built from the same template means. The blank band between them is
# the only signal, and it is the one a reader uses. Applies to the FIRST pair
# of a run, before there is a rhythm to measure against.
_ROW_GAP_FACTOR = 1.6
# ...and after that, how far past the run's own row pitch a line may sit and
# still be the next row. Rows land 12pt apart and the band between two stacked
# tables is 23pt, so the rhythm is what separates them.
_PITCH_FACTOR = 1.5
# a vertical strip this wide that almost no line crosses is a CANDIDATE gutter
_GUTTER_WIDTH = 14.0
# ...and "almost" is the operative word. Demanding a strip empty over the whole
# page height gave a single line the power to weld two columns together for
# good: flexi-p1 prints "PERFORMANCES DU FONDS" across the full width, so the
# gutter below it is crossed once and stops existing, and the table's rows come
# back interleaved with the fiche d'identite printed beside them.
_GUTTER_MAX_CROSSING = 0.1
# ...and it is a real one only when few lines reach across it. Emptiness alone
# does not tell a page gutter from a table's own column gap - both are empty.
# What separates them is that EVERY row of a table reaches across every one of
# its gaps, while lines belonging to two independent page columns almost never
# do.
_GUTTER_MAX_SPANNING = 0.25
# how far either side of a candidate strip counts as "beside" it, as a share of
# the width the page's words occupy. Only the immediate neighbours can say what
# a strip separates: judged against the whole page, a table's own column gap is
# compared with the prose column further right and loses.
_GUTTER_WINDOW = 0.2
# a cell holding this many words is a sentence. Justified prose leaves gaps that
# line up by accident, so alignment alone accepts a paragraph as a table.
_PROSE_WORDS = 4


@dataclass
class WordTable:
    """A detected region, shaped like what `find_tables` returns.

    `detect_tables` and everything downstream reads `.bbox` — the crop is cut
    from it, and the crop is what a reader checks the answer against. Carrying
    the same attribute means the acceptance rules, the crop contract and the
    citation path all apply unchanged."""

    bbox: tuple[float, float, float, float]
    grid: list[list[str]]

    def extract(self) -> list[list[str]]:
        return self.grid


@dataclass
class WordLine:
    """One baseline of the page, already split into cells by its gaps."""

    top: float
    bottom: float
    cells: list[tuple[float, float, str]] = field(default_factory=list)
    # the words themselves, in x order. Cells are a first guess made from gaps
    # alone and are used to decide which lines belong together; the grid is
    # built back from the words, because a gap rule cannot see a column that is
    # narrower than a space (see _MIN_RUN_CELLS).
    words: list[tuple] = field(default_factory=list)

    @property
    def edges(self) -> list[float]:
        return [start for start, _, _ in self.cells]


def column_bands(words: list[tuple], min_gutter: float = _GUTTER_WIDTH
                 ) -> list[list[tuple]]:
    """The page's independent columns, split where few lines reach across.

    Without this, a row of the risk table and a line of the market commentary
    printed beside it share a baseline and are read as one row:

        ['Tracking error (en %)', '0,12', '0,36', '0,32',
         'annuel autour de 1%. La banque centrale']

    Emptiness alone cannot find the boundary: the gap between two columns of a
    table is just as empty as the gutter between two columns of a page. The
    difference is who reaches across. Every row of a table spans every gap
    inside it — that is what makes it a row. Lines set in two independent page
    columns belong to one or the other, and span nothing.
    """
    if not words:
        return []
    left = min(w[0] for w in words)
    right = max(w[2] for w in words)
    if right - left <= min_gutter:
        return [words]

    step = 2.0
    n_bins = max(int((right - left) / step) + 1, 1)

    def _bin(x: float) -> int:
        return min(max(int((x - left) / step), 0), n_bins - 1)

    # counted per LINE, not per word: what matters is how many lines reach into
    # the strip, and a heading of five words crossing it is still one line.
    lines = group_lines(words)
    crossings = [0] * n_bins
    for line in lines:
        touched: set[int] = set()
        for word in line:
            touched.update(range(_bin(word[0]), _bin(word[2]) + 1))
        for i in touched:
            crossings[i] += 1
    # int() on purpose: with few lines this is 0 and the strip must be truly
    # empty, which is what keeps the synthetic fixtures honest.
    allowed = int(_GUTTER_MAX_CROSSING * len(lines))

    candidates: list[float] = []
    run_start: int | None = None
    for i, count in enumerate([*crossings, n_bins]):
        if count <= allowed:
            run_start = i if run_start is None else run_start
            continue
        if run_start is not None:
            if (i - run_start) * step >= min_gutter:
                candidates.append(left + (run_start + (i - run_start) / 2) * step)
            run_start = None
    window = (right - left) * _GUTTER_WINDOW
    cuts = [cut for cut in candidates
            if _spanning_share(lines, cut, window) <= _GUTTER_MAX_SPANNING]
    if not cuts:
        return [words]

    bands: list[list[tuple]] = [[] for _ in range(len(cuts) + 1)]
    for word in words:
        centre = (word[0] + word[2]) / 2
        bands[sum(1 for cut in cuts if centre > cut)].append(word)
    return [band for band in bands if band]


def _spanning_share(lines: list[list[tuple]], cut: float, window: float) -> float:
    """Of the lines printed either side of this strip, how many reach across?

    Both halves are measured within a WINDOW of the strip, and against the
    BUSIER of the two. Each of those was wrong on its own, and each was wrong on
    a real page:

      - counted over the whole page, everything beyond the strip counts, so the
        gap between two columns of a table is judged against the prose column
        further right and the table is cut into one band per column;
      - counted against the smaller side, flexi-p2 fails. Its left column holds
        NOTHING but the risk table, so six of its eight lines merge with a line
        of the commentary beside them, the share reads 0.75, and the gutter is
        refused - which is how ['Indice de référence', '0,18', '0,34', '0,40',
        'prix enregistrait une progression'] came back as one row.

    Within the window the two sides of a table's own gap are the same rows, so
    the share is 1. The two sides of a page gutter are a handful of rows against
    forty lines of prose, and the share is small however many of them collide.

    1.0 when one side is empty — a cut at the page margin separates nothing.
    """
    left = [line for line in lines
            if any(cut - window <= w[2] <= cut for w in line)]
    right = [line for line in lines
             if any(cut <= w[0] <= cut + window for w in line)]
    if not left or not right:
        return 1.0
    on_right = {id(line) for line in right}
    spanning = sum(1 for line in left if id(line) in on_right)
    return spanning / max(len(left), len(right))


def has_figures(run: list["WordLine"]) -> bool:
    """Does this run carry a number anywhere?

    The second false positive on the real page, and the one `looks_like_prose`
    cannot see, because every cell in it holds a single word:

        ['orientation', '', 'avec', 'des', 'niveaux', '', 'de']

    Justified text stretches its spaces to reach the margin, so on two unlucky
    lines the stretched gaps land within _EDGE_TOLERANCE of each other and the
    lines "align". Nothing about the words themselves says table.

    What every table in this corpus has and that paragraph does not is figures —
    these are fund factsheets, and a table here is a table OF something measured.
    The cost is stated plainly: a borderless table made only of words is refused.
    That is the conservative direction. This runs solely as the last resort after
    `find_tables` returns nothing, so refusing leaves the page exactly as it is
    today, while accepting puts a paragraph into the index as a table — with a
    crop image and a summary asserting it is one.
    """
    return any(any(ch.isdigit() for ch in text)
               for line in run for _, _, text in line.cells)


def looks_like_prose(run: list["WordLine"]) -> bool:
    """Is this run a paragraph whose gaps happen to line up?

    Justified text is the trap: it stretches spaces to reach the margin, so its
    word boundaries fall on similar x positions line after line. What it never
    does is put SHORT cells in those columns."""
    cells = [text for line in run for _, _, text in line.cells]
    if not cells:
        return True
    wordy = sum(1 for text in cells if len(text.split()) >= _PROSE_WORDS)
    return wordy > len(cells) / 2


def group_lines(words: list[tuple], line_tolerance: float = _LINE_TOLERANCE
                ) -> list[list[tuple]]:
    """Words gathered into baselines, top to bottom.

    Grouped on the vertical centre rather than on y0: a superscript or a taller
    glyph shifts the top of a word without moving the line it belongs to."""
    if not words:
        return []
    ordered = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[list[tuple]] = [[ordered[0]]]
    for word in ordered[1:]:
        centre = (word[1] + word[3]) / 2
        last = lines[-1][-1]
        if abs(centre - (last[1] + last[3]) / 2) <= line_tolerance:
            lines[-1].append(word)
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda w: w[0])
    return lines


def split_cells(line: list[tuple], column_gap: float = _COLUMN_GAP) -> WordLine:
    """One baseline cut into cells wherever the words leave a real gap."""
    cells: list[tuple[float, float, str]] = []
    start, end, text = line[0][0], line[0][2], [line[0][4]]
    for word in line[1:]:
        if word[0] - end > column_gap:
            cells.append((start, end, " ".join(text)))
            start, text = word[0], []
        text.append(word[4])
        end = word[2]
    cells.append((start, end, " ".join(text)))
    return WordLine(top=min(w[1] for w in line),
                    bottom=max(w[3] for w in line), cells=cells,
                    words=list(line))


def edges_align(a: WordLine, b: WordLine,
                tolerance: float = _EDGE_TOLERANCE) -> bool:
    """Do these two baselines share a column structure?

    Counted on the SHARED edges, not on all of them: the header row of a real
    table often carries one label fewer than its body ("Portefeuille" against a
    blank corner), and demanding every edge match would split the table right
    under its own header."""
    if len(a.cells) < _MIN_RUN_CELLS or len(b.cells) < _MIN_RUN_CELLS:
        return False
    matched = sum(1 for edge in a.edges
                  if any(abs(edge - other) <= tolerance for other in b.edges))
    return (matched >= min(len(a.edges), len(b.edges)) - 1
            and matched >= _MIN_RUN_CELLS)


def find_word_tables(words: list[tuple], *, column_gap: float = _COLUMN_GAP,
                     min_rows: int = _MIN_ROWS
                     ) -> list[tuple[tuple[float, float, float, float], list[list[str]]]]:
    """Table regions on a page, from word coordinates alone.

    Returns (bbox, grid) pairs in reading order — the same shape `detect_tables`
    already works with, so the acceptance rules and the crop-image contract
    apply unchanged."""
    runs: list[list[WordLine]] = []
    for band in column_bands(words):
        runs.extend(_runs_in_band(band, column_gap, min_rows))

    out = []
    for run in runs:
        if looks_like_prose(run) or not has_figures(run):
            continue
        columns = supported_columns(run)
        if len(columns) < 2 or (len(columns) < _MIN_CELLS
                                and len(run) < _MIN_NARROW_ROWS):
            continue
        grid = [_row_for(line, columns) for line in run]
        bbox = (min(w[0] for line in run for w in line.words),
                min(line.top for line in run),
                max(w[2] for line in run for w in line.words),
                max(line.bottom for line in run))
        out.append((bbox, grid))
    out.sort(key=lambda pair: (pair[0][1], pair[0][0]))
    return out


def _runs_in_band(words: list[tuple], column_gap: float,
                  min_rows: int) -> list[list["WordLine"]]:
    lines = [split_cells(line, column_gap) for line in group_lines(words) if line]
    runs: list[list[WordLine]] = []
    current: list[WordLine] = []
    for line in lines:
        if (current and edges_align(current[-1], line)
                and _row_continues(current, line)):
            current.append(line)
            continue
        if len(current) >= min_rows:
            runs.append(current)
        current = [line] if len(line.cells) >= _MIN_RUN_CELLS else []
    if len(current) >= min_rows:
        runs.append(current)
    return runs


def _row_continues(run: list[WordLine], line: WordLine,
                   factor: float = _PITCH_FACTOR) -> bool:
    """Is this baseline the next ROW of this run, or the start of a new table?

    Judged against the run's own PITCH once there is one. Against the line's
    height instead, vertes-p1 and flexi-p1 returned their three performance
    tables as a single nine-row region: rows sit 12pt apart, the band between
    two tables is 23pt, and 23 <= height * 1.6 holds for any type above about
    9pt. Pitch says the same thing the reader's eye does — the rhythm broke.

    A run of one has no rhythm yet, so the first pair still goes by height."""
    if len(run) < 2:
        height = max(run[-1].bottom - run[-1].top, 1.0)
        return line.top - run[-1].bottom <= height * _ROW_GAP_FACTOR
    pitches = sorted(b.top - a.top for a, b in zip(run, run[1:]))
    pitch = max(pitches[len(pitches) // 2], 1.0)
    return line.top - run[-1].top <= pitch * factor


def supported_columns(run: list[WordLine], tolerance: float = _EDGE_TOLERANCE
                      ) -> list[float]:
    """The x positions that REPEAT down this run — one per real column.

    Built from every word rather than from the cells, and this is the whole
    point. A cell boundary is a guess made from one line in isolation, and one
    line cannot tell the gap between two columns from the gap between two words
    of a label — on rhone-p1 the column gap is the SMALLER of the two. What a
    column has that a word boundary does not is company: "Secteur", "Santé" and
    "Consommation" all start at the same x, while "actions" in the label above
    starts at an x nothing else shares.

    Support is counted per LINE, so a run of two rows needs both, and a longer
    run needs half. A genuine column can be empty on some rows — that is the
    hole `_row_for` exists to preserve — but not on most of them."""
    clusters: list[list[float]] = []
    owners: list[set[int]] = []
    for i, line in enumerate(run):
        for word in line.words:
            for c, xs in enumerate(clusters):
                if abs(word[0] - min(xs)) <= tolerance:
                    xs.append(word[0])
                    owners[c].add(i)
                    break
            else:
                clusters.append([word[0]])
                owners.append({i})
    need = max(2, (len(run) + 1) // 2)
    return sorted(min(xs) for xs, own in zip(clusters, owners) if len(own) >= need)


def _row_for(line: WordLine, columns: list[float]) -> list[str]:
    """This baseline's words placed into the run's columns, blanks included.

    A blank matters: "Indice de référence" with no 10-year figure must leave
    that column EMPTY, not shift every later value one place left — which is
    exactly how a value ends up reported under the wrong header.

    Every word lands somewhere — a word far from any column joins its nearest,
    which is how "actions" rejoins "Valeurs" in the label it belongs to. Nothing
    printed on the line may be dropped: a value the grid discards is a value no
    answer can cite, and the reader has no way to know it was ever there."""
    row = [""] * len(columns)
    for word in line.words:
        best = min(range(len(columns)), key=lambda i: abs(columns[i] - word[0]))
        row[best] = f"{row[best]} {word[4]}".strip() if row[best] else word[4]
    return row
