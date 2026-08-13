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
# a row with fewer than this many cells is prose, not a table row
_MIN_CELLS = 3
# fewer rows than this is not a table, it is a heading and a line under it
_MIN_ROWS = 2
# a vertical gap wider than this many times the line's own height ends the
# table. Columns alone cannot separate two STACKED tables - the second one's
# figures sit under the first one's columns by construction, which is what
# being built from the same template means. The blank band between them is
# the only signal, and it is the one a reader uses.
_ROW_GAP_FACTOR = 1.6


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

    @property
    def edges(self) -> list[float]:
        return [start for start, _, _ in self.cells]


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
                    bottom=max(w[3] for w in line), cells=cells)


def edges_align(a: WordLine, b: WordLine,
                tolerance: float = _EDGE_TOLERANCE) -> bool:
    """Do these two baselines share a column structure?

    Counted on the SHARED edges, not on all of them: the header row of a real
    table often carries one label fewer than its body ("Portefeuille" against a
    blank corner), and demanding every edge match would split the table right
    under its own header."""
    if len(a.cells) < _MIN_CELLS or len(b.cells) < _MIN_CELLS:
        return False
    matched = sum(1 for edge in a.edges
                  if any(abs(edge - other) <= tolerance for other in b.edges))
    return matched >= min(len(a.edges), len(b.edges)) - 1 and matched >= _MIN_CELLS


def find_word_tables(words: list[tuple], *, column_gap: float = _COLUMN_GAP,
                     min_rows: int = _MIN_ROWS
                     ) -> list[tuple[tuple[float, float, float, float], list[list[str]]]]:
    """Table regions on a page, from word coordinates alone.

    Returns (bbox, grid) pairs in reading order — the same shape `detect_tables`
    already works with, so the acceptance rules and the crop-image contract
    apply unchanged."""
    lines = [split_cells(line, column_gap) for line in group_lines(words) if line]
    runs: list[list[WordLine]] = []
    current: list[WordLine] = []
    for line in lines:
        if (current and edges_align(current[-1], line)
                and _vertically_adjacent(current[-1], line)):
            current.append(line)
            continue
        if len(current) >= min_rows:
            runs.append(current)
        current = [line] if len(line.cells) >= _MIN_CELLS else []
    if len(current) >= min_rows:
        runs.append(current)

    out = []
    for run in runs:
        columns = _column_edges(run)
        grid = [_row_for(line, columns) for line in run]
        bbox = (min(c[0] for line in run for c in line.cells),
                min(line.top for line in run),
                max(c[1] for line in run for c in line.cells),
                max(line.bottom for line in run))
        out.append((bbox, grid))
    return out


def _vertically_adjacent(previous: WordLine, line: WordLine,
                         factor: float = _ROW_GAP_FACTOR) -> bool:
    """Is this baseline the next ROW, or the start of something else?"""
    height = max(previous.bottom - previous.top, 1.0)
    return line.top - previous.bottom <= height * factor


def _column_edges(run: list[WordLine], tolerance: float = _EDGE_TOLERANCE
                  ) -> list[float]:
    """One x per column, merged across the run's baselines."""
    edges: list[float] = []
    for line in run:
        for edge in line.edges:
            for i, known in enumerate(edges):
                if abs(edge - known) <= tolerance:
                    edges[i] = min(known, edge)
                    break
            else:
                edges.append(edge)
    return sorted(edges)


def _row_for(line: WordLine, columns: list[float],
             tolerance: float = _EDGE_TOLERANCE) -> list[str]:
    """This baseline's cells placed into the run's columns, blanks included.

    A blank matters: "Indice de référence" with no 10-year figure must leave
    that column EMPTY, not shift every later value one place left — which is
    exactly how a value ends up reported under the wrong header."""
    row = [""] * len(columns)
    for start, _, text in line.cells:
        best = min(range(len(columns)), key=lambda i: abs(columns[i] - start))
        if abs(columns[best] - start) <= tolerance * 2:
            row[best] = (row[best] + " " + text).strip() if row[best] else text
    return row
