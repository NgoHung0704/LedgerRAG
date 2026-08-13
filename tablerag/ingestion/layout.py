"""Layout analysis: split each page into text / table / figure regions.

Detector choice (documented deviation from the spec's PP-Structure default):
for pages WITH a text layer, PyMuPDF's built-in `find_tables` is used — it is
even cheaper than PP-Structure, needs zero extra dependencies, and gives the
grid content for the simple-parser path for free. Scanned pages carry no text
layer, so they take the VLM path entirely (spec Phase 2 §6). If a future
corpus defeats find_tables, a PP-Structure detector can be swapped in behind
`analyze_document` without touching the rest of the pipeline.
"""

from __future__ import annotations

import io
import re
from collections import defaultdict
from dataclasses import dataclass, field

import fitz  # PyMuPDF
from PIL import Image

from tablerag.ingestion.chart_check import bar_groups, chart_bars
from tablerag.ingestion.palette import vector_palette
from tablerag.ingestion.extract import PdfError

# image blocks smaller than this fraction of the page are decorations, not figures
_MIN_FIGURE_AREA_RATIO = 0.005
_CAPTION_MAX_DISTANCE = 60.0  # points below the figure
_CAPTION_MAX_CHARS = 300

# --- layout-heavy page detection -------------------------------------------
# A slide-style page (a process diagram, a comparison grid) reads as a GRID:
# column = topic, row = aspect. Linear text extraction flattens it row by row
# and the association is lost — no reading order recovers it, so such pages are
# flagged for review and can be re-read by the VLM into a structured form.
_LAYOUT_MIN_BLOCKS = 6        # fewer blocks than this is an ordinary page
_LAYOUT_MIN_COLUMNS = 3       # 2 columns of prose read acceptably once sorted
_LAYOUT_MIN_PER_COLUMN = 2    # a column needs stacked content to be a column
_LAYOUT_GUTTER_RATIO = 0.02   # x-gap counting as a column separator, of width


@dataclass
class Region:
    type: str  # 'text' | 'table' | 'figure'
    bbox: tuple[float, float, float, float]
    text: str = ""                                  # text regions
    grid: list[list[str | None]] | None = None      # tables: simple-path extraction
    complex: bool = False                           # tables: classifier verdict
    caption: str | None = None                      # figures
    # tables: region re-rendered straight from the PDF at high DPI — real
    # pixels for the VLM instead of a crop of the 120-dpi page image
    crop_png: bytes | None = None
    # cross-page tables: additional pages this (merged) table continues onto
    span_pages: list[int] = field(default_factory=list)
    # text regions: the page lays its text out in columns (a slide or diagram),
    # so the flattened reading order is not faithful — flagged for review
    layout_suspect: bool = False
    # figures: drawn as vector paths rather than pasted as an image. Its bars
    # have exact coordinates, so what a model reads off it can be CHECKED
    # (see ingestion/chart_check.py)
    vector: bool = False
    bars: list[float] = field(default_factory=list)  # figures: bar lengths
    groups: list[int] = field(default_factory=list)  # figures: bars per category
    # tables/figures: the heading printed above them. A picture is FOUND by the
    # words a reader would use, and those are on the page around it.
    context: str = ""
    # figures: the inks the drawing actually uses, measured not guessed
    palette: list = field(default_factory=list)


@dataclass
class PageLayout:
    page: int  # 1-based
    width: float
    height: float
    image_png: bytes
    is_scan: bool
    regions: list[Region] = field(default_factory=list)


def table_grid_is_complex(grid: list[list[str | None]] | None) -> bool:
    """simple_parser vs vlm classifier — biased toward VLM on any doubt
    (SPEC Phase 2 §2: more expensive but more correct)."""
    if not grid or len(grid) < 2:
        return True
    n_cols = len(grid[0])
    if n_cols < 2:
        return True
    if any(len(row) != n_cols for row in grid):
        return True
    header = grid[0]
    if any(cell is None or not str(cell).strip() for cell in header):
        return True  # gaps in the header usually mean merged multi-level headers
    cells = [cell for row in grid for cell in row]
    empty = sum(1 for cell in cells if cell is None or not str(cell).strip())
    if empty / len(cells) > 0.15:
        return True  # merged/spanned cells surface as empty cells in the grid
    return False


def _overlap_ratio(rect: fitz.Rect, other: fitz.Rect) -> float:
    inter = fitz.Rect(rect) & other
    area = rect.get_area()
    return inter.get_area() / area if area else 0.0


def grid_cell_texts(grid) -> set[str]:
    """Normalized non-trivial cell strings of a detected grid."""
    cells: set[str] = set()
    for row in grid or []:
        for cell in row:
            text = " ".join(str(cell or "").split()).lower()
            if len(text) > 1:
                cells.add(text)
    return cells


def duplicates_table_text(content: str, cell_texts: set[str],
                          min_lines: int = 3, ratio: float = 0.6) -> bool:
    """True when a text block is really a table read as loose lines.

    Geometry alone does not catch this: a block that clips a table edge stays
    under the overlap threshold and drags the whole grid in as unstructured
    text. Measured on the box — the barème of the avenant was indexed BOTH as
    a parsed table and as a text chunk of the same page, and the text copy
    (headerless, 'C 5 24 250') outranked the structured one and produced the
    wrong answer. Comparing content instead of boxes is independent of how
    tightly the detector drew the table.

    Prose is unaffected: sentences do not appear as table cells.
    """
    if not cell_texts:
        return False
    lines = [" ".join(line.split()).lower()
             for line in (content or "").splitlines()]
    lines = [line for line in lines if len(line) > 1]
    if len(lines) < min_lines:
        return False
    hits = sum(1 for line in lines if line in cell_texts)
    return hits / len(lines) >= ratio


# detection strategies from strict to lenient: lines_strict misses tables with
# imperfect borders (common in real HR grids — this is what dropped the second
# table on the CETIAT page), so we also try `lines`, and finally text-alignment
_TABLE_STRATEGIES = ("lines_strict", "lines", "text")


# a grid emptier than this, or holding a cell this long, is a page's layout
# frame rather than a table (measured on a fund factsheet: 0.20 fill, and a
# 606-character cell). Real tables here run to tens of characters a cell.
_LAYOUT_MAX_FILL = 0.25
_LAYOUT_MAX_CELL_CHARS = 400
# cells ending like a sentence. Measured over every grid the ruled strategies
# return on a health-insurance notice: the seven real tables scored 0.00-0.05,
# the six prose-in-a-box ones 0.17-1.00. There is a wide gap and this sits in
# it — no real table on the corpus comes near.
_LAYOUT_MAX_SENTENCE_CELLS = 0.10


def grid_fill_ratio(grid: list[list]) -> float:
    cells = [c for row in grid for c in row]
    if not cells:
        return 0.0
    return sum(1 for c in cells if c is not None and str(c).strip()) / len(cells)


def _filled(row) -> set[int]:
    return {j for j, c in enumerate(row) if c is not None and str(c).strip()}


def repair_grid(grid: list[list]) -> list[list]:
    """Fix two faults find_tables makes, before anything else sees the grid.

    The grid is not just the simple parser's input — it is handed to the VLM
    as evidence, and the VLM reproduces it faithfully. So a broken grid becomes
    a broken table however it is parsed. Both faults were read off the
    justificatif matrices of a health-insurance notice, whose rendered HTML had
    the row labels and the column headers in DIFFERENT columns.

    A COLUMN THAT IS EMPTY EVERYWHERE is a phantom boundary — the detector
    found a gutter where there is no column. It carries nothing, so dropping it
    cannot lose anything.

    A HEADER CELL THAT WRAPS becomes one row per line: "Justificatifs à fournir
    à notre" / "demande en cas de" / "traitement via ou hors" / "NOEMIE" came
    back as four rows, three of them holding a single cell and nine blanks.
    They are folded back into the header.

    The fold is bounded by the row LABEL, which is what makes it safe: only
    rows before the first one with content in column 0 are considered, and only
    when their filled columns are a subset of the header's. A sparse data row
    like "Ordonnance médicale" has a label, so it is never swallowed.
    """
    if not grid:
        return grid
    width = max(len(row) for row in grid)
    keep = [j for j in range(width)
            if any(str(row[j] or "").strip() for row in grid if j < len(row))]
    if not keep:
        return grid
    grid = [[row[j] if j < len(row) else None for j in keep] for row in grid]

    if len(grid) < 2:
        return grid
    header, folded = list(grid[0]), 1
    while folded < len(grid):
        row = grid[folded]
        cells = _filled(row)
        if not cells or 0 in cells or not cells <= _filled(header):
            break
        for j in cells:
            header[j] = f"{header[j]} {row[j]}".strip()
        folded += 1
    grid = [header, *grid[folded:]]

    # A COLUMN HOLDING A HEADER AND NOTHING ELSE is the neighbouring column's
    # header, split off by a phantom boundary. This is what put the row labels
    # and the column headers in different columns: "Justificatifs à fournir à
    # notre demande…" sat alone in column 1 while every row label sat in column
    # 0 under an empty header. Measured over both corpus documents — every
    # genuine column has at least one filled data cell, without exception, and
    # the four that do not are all of this kind.
    for j in range(len(grid[0]) - 1, 0, -1):
        head_j = str(grid[0][j] or "").strip()
        if not head_j or str(grid[0][j - 1] or "").strip():
            continue
        if any(str(row[j] or "").strip() for row in grid[1:]):
            continue                       # a real column, however sparse
        grid[0][j - 1] = head_j
        for row in grid:
            del row[j]
    return grid


def sentence_cell_ratio(grid: list[list]) -> float:
    """Share of filled cells that end the way a SENTENCE ends.

    A table cell ends with a name, a number, a unit, a footnote marker — never
    with a full stop. Prose set inside a bordered box does, and that is what
    the ruled strategies keep returning: the lexicon, the definitions, the
    exclusions list, "NE SONT PAS REMBOURSÉS :" and its bullets."""
    cells = [str(c).strip() for row in grid for c in row if c and str(c).strip()]
    if not cells:
        return 0.0
    return sum(1 for c in cells if c.endswith((".", ",", ";"))) / len(cells)


def looks_like_page_layout(grid: list[list]) -> bool:
    """Is this "table" really a page's layout frame?

    The ruled strategies find one wherever a page is built out of boxes, and a
    fund factsheet gave two on its first page: a 5x2 whose ten cells held the
    title and the date, and a 7x5 whose cells held whole paragraphs — 606
    characters in one of them. Both reached the VLM, which refused them (they
    are not tables), and both then sat in Review forever.

    Two independent signs, either of which settles it:
      - three cells in four are empty — a grid that is mostly holes is a
        frame. The line is drawn below the sparsest RULED table the suite
        already accepts, so a merged-cell table keeps coming through;
      - one cell holds a paragraph — a data cell is a value, not a page of
        prose. Real tables in this corpus run to tens of characters a cell.
    """
    cells = [str(cell or "") for row in grid for cell in row]
    filled = [cell for cell in cells if cell.strip()]
    if not filled:
        return True
    return (grid_fill_ratio(grid) < _LAYOUT_MAX_FILL
            or max(len(cell) for cell in filled) > _LAYOUT_MAX_CELL_CHARS
            or sentence_cell_ratio(grid) > _LAYOUT_MAX_SENTENCE_CELLS)


# two decimals with nothing between them but space: '-0,82 0,8' is two columns
# that were never separated. "de 2,5 à 3,5" has a word between them and is one
# cell; "1 234,56" is one number with one comma; "1,52% Santé" is a value and a
# label. None of those match.
_SLICED_APART = re.compile(r"-?\d+,\d+\s+-?\d+[,.]?\d*")
# ...and a cell that BEGINS with the separator: 4,79 cut into '4' and ',79'
_SLICED_MID_NUMBER = re.compile(r"^\s*[.,]\d")


def cuts_through_numbers(grid: list[list]) -> bool:
    """Did the column boundaries land INSIDE the rows rather than between them?

    The lenient `text` strategy returned these on the fund factsheets:

        ['3 -1,91 -1,0', '4,96 2,4', '3 18,60']
        [',79 3,89', '4,68']

    A cell beginning with a comma is a value cut in half — 4,79 became "4" and
    ",79" in the next column. Two decimals with nothing between them but space
    are two columns that were never separated. Either way the row was sliced
    through its values, and the grid is not a reading of the table but a
    mangling of it; it goes into the index all the same, and its rectangle then
    vetoes any better region covering the same table.

    This was first written for the lenient `text` strategy only, on the argument
    that a ruled cell boundary was drawn on the page and so must be believed.
    vertes-p1 then vetoed all three of its performance tables with three RULED
    fragments, each of which cut a value in half. A boundary that lands inside a
    number is wrong whoever drew it.

    What must survive: "de 2,5 à 3,5" has a word between its decimals, "1 234,56"
    is one number with one comma, "1,52% Santé" is a value and a label.
    """
    return any(_SLICED_APART.search(text) or _SLICED_MID_NUMBER.search(text)
               for row in grid for cell in row
               if (text := str(cell or "")))


def accept_table(rect: fitz.Rect, grid: list[list], strategy: str,
                 existing: list[fitz.Rect]) -> bool:
    """Keep a detected table region? Dedupe against already-accepted regions
    and reject non-table shapes — especially guard the lenient `text` strategy
    so prose/columns aren't mistaken for a table."""
    if rect.get_area() <= 0 or not grid:
        return False
    if any(_overlap_ratio(rect, ex) > 0.5 or _overlap_ratio(ex, rect) > 0.5
           for ex in existing):
        return False
    n_cols = max((len(row) for row in grid), default=0)
    if n_cols < 2 or len(grid) < 2:  # need a real 2-D grid
        return False
    if looks_like_page_layout(grid):
        return False
    if strategy == "text" and grid_fill_ratio(grid) < 0.6:
        return False  # sparse -> probably prose, not a table
    if strategy != "words" and cuts_through_numbers(grid):
        # not applied to the word detector: there it would drop the only
        # reading of a table, while here it drops a wrong reading that is
        # vetoing a right one
        return False
    return True


def diagnose_page_tables(page: fitz.Page) -> dict:
    """Per-strategy detection breakdown for one page — powers the Diagnostics
    UI so a missing real-document table can be debugged without shell access."""
    strategies: dict[str, dict] = {}
    for strat in _TABLE_STRATEGIES:
        try:
            tables = page.find_tables(strategy=strat).tables
        except Exception as e:  # noqa: BLE001
            strategies[strat] = {"error": str(e), "count": 0, "tables": []}
            continue
        items = []
        for t in tables:
            grid = repair_grid(t.extract())
            items.append({
                "bbox": [round(x, 1) for x in t.bbox],
                "rows": len(grid),
                "cols": max((len(r) for r in grid), default=0),
                "fill": round(grid_fill_ratio(grid), 2),
                "accept": accept_table(fitz.Rect(t.bbox), grid, strat, []),
            })
        strategies[strat] = {"count": len(tables), "tables": items}
    kept = detect_tables(page)
    return {
        "width": round(page.rect.width),
        "height": round(page.rect.height),
        "text_chars": len(page.get_text("text").strip()),
        "strategies": strategies,
        "kept": [{"bbox": [round(x, 1) for x in t.bbox], "rows": len(g),
                  "cols": max((len(r) for r in g), default=0),
                  "complex": table_grid_is_complex(g)} for t, g in kept],
    }


def diagnose_pdf_tables(pdf_bytes: bytes) -> list[dict]:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return [diagnose_page_tables(page) for page in doc]


def resolve_by_quality(candidates: list[tuple]) -> list[int]:
    """Pick winners among possibly-overlapping candidates by GRID QUALITY,
    not by strategy order. candidates: (cells, area, priority, rect) tuples;
    returns indices of the kept ones.

    Measured necessity (Cotation emplois CETIAT): lines_strict detected a
    TRUNCATED region (7x3 blob, right column cut) while `lines` found the full
    19x4 grid — first-strategy-wins kept the truncated one. Ranking: more
    cells (finer real structure beats a blob), then larger area (fuller
    coverage), then strategy priority (strict wins exact ties)."""
    order = sorted(range(len(candidates)),
                   key=lambda i: (candidates[i][0], candidates[i][1],
                                  -candidates[i][2]),
                   reverse=True)
    kept: list[int] = []
    kept_rects: list = []
    for i in order:
        rect = candidates[i][3]
        if any(_overlap_ratio(rect, ex) > 0.5 or _overlap_ratio(ex, rect) > 0.5
               for ex in kept_rects):
            continue
        kept.append(i)
        kept_rects.append(rect)
    return kept


def detect_tables(page: fitz.Page) -> list[tuple]:
    """Every table region on the page. Line-based strategies (lines_strict,
    lines) compete on quality; the lenient `text` strategy only fills gaps
    where they found nothing (it exists to catch borderless tables, never to
    override a ruled detection). Returns (table, grid) pairs in reading order.
    A detector crash on one strategy must not kill the page."""
    line_candidates: list[tuple] = []   # (cells, area, priority, rect)
    line_payloads: list[tuple] = []     # (table, grid)
    for priority, strategy in enumerate(("lines_strict", "lines")):
        try:
            tables = page.find_tables(strategy=strategy).tables
        except Exception:  # noqa: BLE001
            continue
        for table in tables:
            try:
                grid = table.extract()
            except Exception:  # noqa: BLE001
                continue
            rect = fitz.Rect(table.bbox)
            n_cols = max((len(row) for row in grid), default=0) if grid else 0
            if rect.get_area() <= 0 or n_cols < 2 or len(grid) < 2:
                continue
            # the ruled strategies find a "table" wherever a page is built out
            # of boxes; that check used to guard only the lenient strategy, so
            # a page frame came through here and became an element
            if looks_like_page_layout(grid):
                continue
            # a ruled region can be sliced through its values too - vertes-p1
            # vetoed all three performance tables with three of them
            if cuts_through_numbers(grid):
                continue
            line_candidates.append(
                (len(grid) * n_cols, rect.get_area(), priority, rect))
            line_payloads.append((table, repair_grid(grid)))

    found = [line_payloads[i] for i in resolve_by_quality(line_candidates)]
    rects = [fitz.Rect(table.bbox) for table, _ in found]

    try:
        text_tables = page.find_tables(strategy="text").tables
    except Exception:  # noqa: BLE001
        text_tables = []
    for table in text_tables:
        try:
            grid = table.extract()
        except Exception:  # noqa: BLE001
            continue
        rect = fitz.Rect(table.bbox)
        if accept_table(rect, grid, "text", rects):
            found.append((table, repair_grid(grid)))
            rects.append(rect)

    # Word coordinates, run on every page whatever the other strategies managed.
    # Measured with `make eval-detection`: find_tables reaches 25% of real
    # factsheet pages, not because it reads cells badly but because it cannot
    # tell where a borderless table starts and ends once a page holds more than
    # one thing. Word coordinates can (see word_tables), and they still yield a
    # bbox, so the crop contract survives.
    #
    # This used to run only where the page came up COMPLETELY empty, and that
    # was worth 25% -> 33% and no further: on six of the seven pages still
    # failing, something had been detected — flexi-p2 1/2, rhone-p1 3/4,
    # monetaire-p1 3/4 — so the borderless table that was missing was never
    # looked for. One ruled table on a page was enough to shield every
    # borderless one on it.
    #
    # What makes running it everywhere safe is the dedupe already in
    # accept_table: a region covering more than half of one already accepted is
    # dropped, so a table the ruled strategies read properly keeps their reading
    # and is not re-detected from its words.
    from tablerag.ingestion.word_tables import WordTable, find_word_tables

    try:
        words = page.get_text("words")
    except Exception:  # noqa: BLE001 — detection must not kill the page
        words = []
    for bbox, grid in find_word_tables(words):
        rect = fitz.Rect(bbox)
        repaired = repair_grid(grid)
        if accept_table(rect, repaired, "words", rects):
            found.append((WordTable(bbox=bbox, grid=repaired), repaired))
            rects.append(rect)

    found.sort(key=lambda pair: (pair[0].bbox[1], pair[0].bbox[0]))
    return found


# --- vector figures -------------------------------------------------------
# A chart emitted by PowerPoint/Excel is not an image block: it is vector paths
# plus text, and the text is often OUTLINED (drawn as curves), so its numbers
# are in NO text layer at all. Measured on a fund factsheet: 0 image blocks and
# 281/312/59 vector paths across three pages, with every value in every chart
# unextractable — about fifty numbers that ingestion simply lost.
_VEC_MERGE_GAP = 8.0          # points; paths closer than this are one picture
# 3, not more: a doughnut chart is three arcs. Measured on the factsheet, a
# threshold of 6 was exactly what dropped it.
_VEC_MIN_PATHS = 3
_VEC_MIN_WIDTH = 60.0
_VEC_MIN_HEIGHT = 40.0
_VEC_PANEL_AREA_RATIO = 0.12  # bigger than this is a background, not a mark
_VEC_RULE_WIDTH_RATIO = 0.45  # a wide, flat rect is a separator
_VEC_RULE_HEIGHT = 4.0
_VEC_UNIFORM_TOL = 1.0        # points; below this two rects are "the same size"
_VEC_BAND_MIN_HEIGHT = 3.0    # taller than a hairline: a row band, not a rule
_VEC_MIN_BANDS = 4            # below this, equal heights are a coincidence
_VEC_BAND_MAJORITY = 0.6      # this share sharing one height = rows, not bars
_VEC_TABLE_IOU = 0.5          # a cluster IS a table only if they coincide
_LEGEND_REACH = 1.5           # of the figure's width: how far its key may sit
_LEGEND_MAX_PATHS = 12        # above this a figure carries its own labels


def _iou(a: fitz.Rect, b: fitz.Rect) -> float:
    """Intersection over union — how much two regions ARE each other."""
    inter = (fitz.Rect(a) & b).get_area()
    union = a.get_area() + fitz.Rect(b).get_area() - inter
    return inter / union if union > 0 else 0.0


def _drawing_marks(page: fitz.Page) -> list[fitz.Rect]:
    """Vector paths with the page's DECORATION removed.

    Without this every chart merges into the coloured header and the grey side
    panel that bridge them, and one cluster comes back covering the page."""
    page_area = page.rect.get_area()
    marks = []
    for drawing in page.get_drawings():
        rect = fitz.Rect(drawing["rect"])
        if rect.get_area() > _VEC_PANEL_AREA_RATIO * page_area:
            continue                                    # panel / background
        if (rect.width > _VEC_RULE_WIDTH_RATIO * page.rect.width
                and rect.height < _VEC_RULE_HEIGHT):
            continue                                    # separator rule
        if rect.width < 1 and rect.height < 1:
            continue                                    # artefact
        marks.append(rect)
    return marks


def cluster_rects(rects: list[fitz.Rect],
                  gap: float = _VEC_MERGE_GAP) -> list[tuple[fitz.Rect, int]]:
    """Merge rects whose inflated boxes touch. Returns (bbox, path count)."""
    groups: list[list] = [[fitz.Rect(r), 1] for r in rects]
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i][0], groups[j][0]
                if (a + (-gap, -gap, gap, gap)).intersects(
                        b + (-gap, -gap, gap, gap)):
                    groups[i] = [a | b, groups[i][1] + groups[j][1]]
                    del groups[j]
                    merged = True
                    break
            if merged:
                break
    return [(g[0], g[1]) for g in groups]


def looks_like_table_striping(rects: list[fitz.Rect]) -> bool:
    """Is this cluster a table's alternating row backgrounds?

    Those are row bands of one HEIGHT — a borderless table already extracted
    as text, which must not come back as a "figure" and be described a second
    time. A bar chart is the opposite: its whole point is that the bars differ.

    Widths are not part of the test: a striped table with two column blocks
    draws two widths per row, and requiring one width missed it. Hairlines are
    excluded — a line chart's gridlines are perfectly uniform, and testing
    them threw the chart away. The test is on the DOMINANT height rather than
    the spread, because a header band is taller than the rows under it and
    that one outlier was enough to let a table through."""
    bands = [r for r in rects if r.height >= _VEC_BAND_MIN_HEIGHT]
    if len(bands) < _VEC_MIN_BANDS:
        return False
    tally: dict[float, int] = defaultdict(int)
    for band in bands:
        tally[round(band.height / _VEC_UNIFORM_TOL)] += 1
    return max(tally.values()) / len(bands) >= _VEC_BAND_MAJORITY


def with_legend(box: fitz.Rect, paths: int,
                aside: list[fitz.Rect]) -> fitz.Rect:
    """Grow a figure to take in a key drawn beside it.

    A doughnut's key sits in its own cluster — 30 points tall, under the size
    floor — so it was dropped, and the crop reaching the model held the ring
    without a single label. It said, correctly, that nothing was labelled, and
    the figure was written off as decorative: three values lost because the
    key was standing next to the picture instead of inside it.

    Only a figure of very FEW paths reaches out. That is what says its labels
    cannot be inside it: a doughnut is three arcs, while a line chart carrying
    its own axis is two hundred. Without that condition the line chart reached
    across the page and swallowed the risk scale in the next column, which sat
    23 points away and looked exactly like a key."""
    if paths > _LEGEND_MAX_PATHS:
        return box
    grown = fitz.Rect(box)
    for other in aside:
        if other.y1 < box.y0 or other.y0 > box.y1:
            continue                              # not level with the figure
        gap = max(other.x0 - box.x1, box.x0 - other.x1, 0.0)
        if gap <= _LEGEND_REACH * box.width:
            grown |= other
    return grown


# a sentence: long enough and with enough words that no chart label is one
_PROSE_MIN_CHARS = 40
_PROSE_MIN_SPACES = 5
_VEC_MAX_TABLE_COVER = 0.5


def drawn_around_text(page: fitz.Page, box: fitz.Rect,
                      table_rects: list[fitz.Rect]) -> bool:
    """Is this cluster a frame around content that is already indexed?

    A PICTURE DOES NOT CONTAIN PROSE. That is the whole test, and it is the
    third one tried — the first two were measured and thrown away, which is
    worth recording so they are not tried again:

      - text COVERAGE of the box: real charts measure 0% because their labels
        are outlined curves, but the junk ran 18-72% and one genuine chart hit
        27%, so no threshold separated them.
      - NEW WORDS in the description against the page text: a banner scored
        0.40 and a real matrix 0.76, which looked clean until a banner on a
        near-empty page scored 0.84. It also costs a VLM call to find out.

    Prose separates them because it is a property of what the region IS. A
    chart's labels are "Industries", "27,6", "Portefeuille" — never sentences.
    A banner, a callout, a bordered paragraph contains one. Measured over both
    corpus documents: 27 of 30 junk clusters rejected, and every one of the
    five real charts kept.

    Tables filling the box are the second half. One cluster covered the whole
    tableau de garantie, already three table elements; the veto above compares
    the cluster to ONE table and a quarter-sized table never trips it.
    """
    for block in page.get_text("blocks"):
        if block[6] != 0 or not box.contains(fitz.Rect(block[:4])):
            continue
        text = " ".join(str(block[4] or "").split())
        if len(text) >= _PROSE_MIN_CHARS and text.count(" ") >= _PROSE_MIN_SPACES:
            return True
    area = box.get_area()
    if area <= 0:
        return True
    # against the UNION, and by IoU — not by how much of the box is covered.
    # A page-wide bogus region from find_tables covers a chart completely
    # without being it, and vetoing on that hid every chart on the factsheet
    # (test_a_page_wide_bogus_table_does_not_swallow_the_charts_under_it).
    # Coincidence is mutual; coverage is not.
    inside = [tr for tr in table_rects if (box & tr).get_area() > 0]
    if not inside:
        return False
    covered = sum((box & tr).get_area() for tr in inside)
    union = area + sum(tr.get_area() for tr in inside) - covered
    return union > 0 and covered / union > _VEC_MAX_TABLE_COVER


def detect_vector_figures(page: fitz.Page,
                          table_rects: list[fitz.Rect]) -> list[Region]:
    """Charts drawn as vector paths — invisible to the image-block rule."""
    marks = _drawing_marks(page)
    if not marks:
        return []
    clusters = cluster_rects(marks)
    aside = [box for box, count in clusters
             if count < _VEC_MIN_PATHS
             or box.width < _VEC_MIN_WIDTH or box.height < _VEC_MIN_HEIGHT]

    regions: list[Region] = []
    for box, count in clusters:
        if count < _VEC_MIN_PATHS:
            continue
        if box.width < _VEC_MIN_WIDTH or box.height < _VEC_MIN_HEIGHT:
            continue
        box = with_legend(box, count, aside)
        # a bordered table is also a cluster of paths; it is already an
        # element, and describing its picture would duplicate it. The test is
        # COINCIDENCE, not overlap: find_tables can return a bogus region
        # covering most of the page (it does on the factsheet this was built
        # from), and mere overlap let that swallow every chart under it.
        if any(_iou(box, tr) > _VEC_TABLE_IOU for tr in table_rects):
            continue
        inside = [r for r in marks if box.contains(r)]
        if looks_like_table_striping(inside):
            continue
        if drawn_around_text(page, box, table_rects):
            continue
        # measured HERE because this is where the fitz page lives; ingestion
        # only ever sees the page image
        regions.append(Region(type="figure", bbox=tuple(box), vector=True,
                              bars=chart_bars(page, tuple(box)),
                              groups=bar_groups(page, tuple(box)),
                              palette=vector_palette(page, tuple(box))))
    # reading order, so a figure keeps its position between runs — the eval
    # gate addresses them by index
    regions.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
    return regions


_HEADING_MAX_GAP = 90.0     # points above the region
_HEADING_MAX_CHARS = 160    # longer than this is a paragraph, not a title


def embedded_images(page: fitz.Page) -> list[fitz.Rect]:
    """Where the page's raster images actually sit.

    get_text("blocks") reports an image as a block only sometimes: an image
    placed through a form XObject — what InDesign and most professional layout
    tools emit — never appears there at all. Measured on a health-insurance
    notice: 5 of its 32 pages carry an image and NOT ONE is a block, including
    the page whose lens classification is a grid of coloured cells with no
    ruling and almost no text. Asking the page for its images finds them.
    """
    seen: list[fitz.Rect] = []
    for xref, *_ in page.get_images(full=True):
        try:
            rects = page.get_image_rects(xref)
        except Exception:  # noqa: BLE001 — one odd image must not fail a page
            continue
        for rect in rects:
            rect = fitz.Rect(rect) & page.rect
            if rect.is_empty or rect.get_area() <= 0:
                continue
            if any(_overlap_ratio(rect, other) > 0.5 for other in seen):
                continue
            seen.append(rect)
    return seen


_BULLET = re.compile(r"^[\W_]*[■▪●•◆‣–—-]")
_LEADERS = re.compile(r"\.\s*\.\s*\.")


def looks_like_heading(text: str) -> bool:
    """Is this line a HEADING, or just the nearest short text above?

    Excluding other elements' text was not enough. Measured in a parse export,
    these four went into indexed chunks as though they named the thing below:

        "LES CAS PARTICULIERS DE MAINTIEN … ............... 29"   a contents line
        "■ et, que son tarif soit publiquement affiché."          a bullet
        "délégation)"                                            half a word
        "Seules les garanties prévues au(x) tableau(x) … ci-après."  a sentence

    Four properties settle every one of them, and keep every real heading in
    the corpus: no bullet, no dot leaders, starts with a capital (a fragment
    continuing from the line above does not), and does not end in a full stop.
    A colon is fine — "Ce remboursement peut nécessiter … suivantes :" really
    does introduce the table under it.
    """
    if not text or _BULLET.match(text) or _LEADERS.search(text):
        return False
    return text[:1].isupper() and not text.endswith(".")


def nearest_heading(text_blocks, bbox, taken=()) -> str | None:
    """The short line printed just above a region — the words a reader would
    use to ask for it.

    Retrieval matches the text of a chunk, and a figure's chunk holds only
    what a model saw INSIDE the picture. The question is asked in the
    document's vocabulary, which is printed around it: a booklet's allocation
    grid says nothing about "gestion pilotée" or which risk profile it is, and
    a chart whose own title is drawn as curves carries no words at all.

    `taken` is every region already claimed. A heading belongs to NO element,
    and without that test the nearest text above a stacked table is the bottom
    row of the table before it. Measured on a health-insurance notice, where it
    put three summaries under the wrong subject outright: the optique table was
    summarised as "Tableau sur le scanner, pose d'implant, pilier implantaire",
    which is the last row of the DENTAL table above it. Summaries are what
    routing matches, so a contaminated one sends the question to the wrong
    table — worse than no heading at all.
    """
    x0, y0, x1, _ = bbox
    best, best_gap = None, _HEADING_MAX_GAP
    for block in text_blocks:
        text = " ".join(str(block[4] or "").split())
        if not text or len(text) > _HEADING_MAX_CHARS:
            continue
        if not looks_like_heading(text):
            continue
        gap = y0 - block[3]
        if not 0 <= gap < best_gap:
            continue
        if block[0] > x1 or block[2] < x0:      # not above THIS region
            continue
        block_rect = fitz.Rect(block[:4])
        if any(_overlap_ratio(block_rect, fitz.Rect(box)) > 0.5
               for box in taken):
            continue                            # it is another element's text
        best, best_gap = text, gap
    return best


def looks_like_column_layout(boxes: list[tuple[float, float, float, float]],
                             page_width: float) -> bool:
    """Does this page lay its text out in columns (a slide / diagram grid)?

    Pure geometry, so it is testable without a PDF: cluster the blocks' x-spans
    into columns separated by empty gutters, and call it a column layout when
    at least `_LAYOUT_MIN_COLUMNS` of them each stack `_LAYOUT_MIN_PER_COLUMN`
    blocks. Such a page reads correctly only as a grid, so the caller flags it
    for review instead of pretending the flattened text is faithful."""
    if len(boxes) < _LAYOUT_MIN_BLOCKS or page_width <= 0:
        return False
    gutter = page_width * _LAYOUT_GUTTER_RATIO

    # sweep the x-axis: a column is a maximal run of horizontally overlapping
    # blocks; a gap wider than `gutter` starts a new one
    columns: list[list[tuple[float, float, float, float]]] = []
    current: list[tuple[float, float, float, float]] = []
    edge = None
    for box in sorted(boxes, key=lambda b: b[0]):
        if edge is not None and box[0] - edge > gutter:
            columns.append(current)
            current = []
        current.append(box)
        edge = max(edge or box[2], box[2])
    if current:
        columns.append(current)

    stacked = [c for c in columns if len(c) >= _LAYOUT_MIN_PER_COLUMN]
    return len(stacked) >= _LAYOUT_MIN_COLUMNS


def analyze_page(page: fitz.Page, dpi: int, min_chars: int,
                 table_dpi: int = 240) -> PageLayout:
    text = page.get_text("text")
    png = page.get_pixmap(dpi=dpi).tobytes("png")
    rect = page.rect
    layout = PageLayout(page=page.number + 1, width=rect.width,
                        height=rect.height, image_png=png,
                        is_scan=len(text.strip()) < min_chars)
    if layout.is_scan:
        return layout  # no text layer: the whole page goes down the VLM path

    # --- tables (real pages often have several per page + imperfect borders) ---
    table_rects: list[fitz.Rect] = []
    table_cells: set[str] = set()
    for table, grid in detect_tables(page):
        clip = (fitz.Rect(table.bbox) + (-6, -6, 6, 6)) & page.rect
        layout.regions.append(Region(
            type="table", bbox=tuple(table.bbox), grid=grid,
            complex=table_grid_is_complex(grid),
            crop_png=page.get_pixmap(dpi=table_dpi, clip=clip).tobytes("png")))
        table_rects.append(fitz.Rect(table.bbox))
        table_cells |= grid_cell_texts(grid)

    # --- text + figures (blocks not covered by a table) ---
    # get_text("blocks") yields content-stream order, which for a PowerPoint- or
    # Word-derived PDF is SHAPE order: a slide title can arrive last. Sort by
    # position so the text reads down the page. (This restores document order;
    # it cannot recover a 2-D diagram's column association — that is what the
    # layout flag + VLM re-read are for.)
    blocks = sorted(page.get_text("blocks"), key=lambda b: (round(b[1], 1), b[0]))
    text_blocks = [b for b in blocks if b[6] == 0]
    text_parts: list[str] = []
    text_bbox: fitz.Rect | None = None
    figures: list[Region] = []
    kept_boxes: list[tuple[float, float, float, float]] = []

    for block in blocks:
        block_rect = fitz.Rect(block[:4])
        if any(_overlap_ratio(block_rect, tr) > 0.5 for tr in table_rects):
            continue
        if block[6] == 1:  # image block
            if block_rect.get_area() >= _MIN_FIGURE_AREA_RATIO * rect.get_area():
                figures.append(Region(type="figure", bbox=tuple(block_rect)))
            continue
        content = block[4].strip()
        # a table already indexed as a structured element must not be indexed
        # again as loose text: the text copy has no headers and can outrank it
        if content and duplicates_table_text(content, table_cells):
            continue
        if content:
            text_parts.append(content)
            kept_boxes.append(tuple(block_rect))
            text_bbox = block_rect if text_bbox is None else text_bbox | block_rect

    # images the block scan never reported — most of them, on a professionally
    # laid-out PDF
    for image_rect in embedded_images(page):
        if image_rect.get_area() < _MIN_FIGURE_AREA_RATIO * rect.get_area():
            continue
        if any(_overlap_ratio(image_rect, tr) > 0.5 for tr in table_rects):
            continue
        if any(_overlap_ratio(image_rect, fitz.Rect(f.bbox)) > 0.5
               for f in figures):
            continue
        figures.append(Region(type="figure", bbox=tuple(image_rect)))

    # nearest short text block below each figure = its caption (C5: keep
    # image + caption, nothing more)
    for figure in figures:
        fig_rect = fitz.Rect(figure.bbox)
        best, best_dy = None, _CAPTION_MAX_DISTANCE
        for block in text_blocks:
            content = block[4].strip()
            if not content or len(content) > _CAPTION_MAX_CHARS:
                continue
            block_rect = fitz.Rect(block[:4])
            dy = block_rect.y0 - fig_rect.y1
            horizontal = block_rect.x0 < fig_rect.x1 and block_rect.x1 > fig_rect.x0
            if 0 <= dy < best_dy and horizontal:
                best, best_dy = content, dy
        figure.caption = best

    if text_parts:
        layout.regions.append(Region(
            type="text", bbox=tuple(text_bbox), text="\n\n".join(text_parts),
            layout_suspect=looks_like_column_layout(kept_boxes, rect.width)))
    layout.regions.extend(figures)

    # charts drawn as vector paths — no image block, so nothing above sees
    # them. Skip any that a raster figure already covers.
    for region in detect_vector_figures(page, table_rects):
        box = fitz.Rect(region.bbox)
        if any(_overlap_ratio(box, fitz.Rect(f.bbox)) > 0.3 for f in figures):
            continue
        layout.regions.append(region)
    layout.regions.sort(key=lambda r: (r.bbox[1], r.bbox[0]))

    # What each table and figure sits UNDER. Done LAST, once every region
    # exists: run earlier it only reached the tables, because figures are
    # appended after it, and every figure in the corpus came out with no
    # context at all. A picture is retrieved by the words a reader would use,
    # and those are printed around it, not in it — a chart whose own title is
    # outlined carries no words whatsoever.
    claimed = [r.bbox for r in layout.regions if r.type in ("table", "figure")]
    for region in layout.regions:
        if region.type in ("table", "figure"):
            region.context = nearest_heading(
                text_blocks, region.bbox,
                [b for b in claimed if b != region.bbox]) or ""
    return layout


# ---- cross-page table merging (text-layer PDFs) ---------------------------
# A table that continues onto the next page shows up as: a region ending near
# the bottom of page N + a region starting near the top of page N+1 with
# compatible columns. Merged deterministically: grids concatenated (repeated
# header dropped), crops stitched vertically, parsed once as one table.
# NOTE: SPEC Phase 2 declared cross-page tables out of MVP scope; the project
# owner explicitly widened scope (frequent in the real corpus). Scanned PDFs
# are not merged yet — their regions only exist at ingest time, not here.

_BOTTOM_FRAC = 0.85   # table must end in the last 15% of the page
_TOP_FRAC = 0.18      # continuation must start in the first 18% of the page
_MIN_X_OVERLAP = 0.7  # horizontal footprint must match


def _x_overlap_frac(a: tuple, b: tuple) -> float:
    inter = min(a[2], b[2]) - max(a[0], b[0])
    narrower = min(a[2] - a[0], b[2] - b[0])
    return inter / narrower if narrower > 0 else 0.0


def _norm_row(row: list) -> list[str]:
    return [str(c).strip().lower() if c else "" for c in row]


def _blank(value) -> bool:
    return value is None or not str(value).strip()


def merge_grids(top: list[list] | None,
                bottom: list[list] | None) -> list[list] | None:
    """Concatenate two grid fragments. A repeated header row on the
    continuation page is dropped, and the SEAM is healed: continuation pages
    don't reprint the labels of a group that was cut mid-way, so blank cells
    forming the leading (left) prefix of the first continuation rows inherit
    the column's last label from the previous fragment — per column, until
    that column gets a value of its own. Only letter-labels are carried
    (numbers are data, never duplicated across pages); blanks sitting to the
    right of content are untouched (genuinely empty cells)."""
    if not top or not bottom:
        return top or bottom
    if _norm_row(bottom[0]) == _norm_row(top[0]):
        bottom = bottom[1:]
    if not bottom:
        return top

    n_cols = max(len(row) for row in top + bottom)
    carry: dict[int, str] = {}
    for c in range(n_cols):
        for row in reversed(top):
            if c < len(row) and not _blank(row[c]):
                value = str(row[c]).strip()
                if any(ch.isalpha() for ch in value):
                    carry[c] = value
                break

    healed: list[list] = []
    for row in bottom:
        padded = list(row) + [None] * (n_cols - len(row))
        original = list(padded)
        for c in range(n_cols):
            if _blank(original[c]):
                is_leading_prefix = all(_blank(original[k]) for k in range(c))
                if c in carry and is_leading_prefix:
                    padded[c] = carry[c]
            else:
                carry.pop(c, None)  # the column speaks for itself again
        healed.append(padded)
    return top + healed


def _tables_continue(last: Region, cur_height: float,
                     first: Region, nxt_height: float) -> bool:
    if last.bbox[3] < _BOTTOM_FRAC * cur_height:
        return False
    if first.bbox[1] > _TOP_FRAC * nxt_height:
        return False
    if _x_overlap_frac(last.bbox, first.bbox) < _MIN_X_OVERLAP:
        return False
    if last.grid and first.grid:
        cols_a = max(len(r) for r in last.grid)
        cols_b = max(len(r) for r in first.grid)
        if cols_a != cols_b:
            return False
        if restarts(last.grid, first.grid):
            return False
    return True


def restarts(top: list[list], nxt: list[list]) -> bool:
    """Does the next page BEGIN AGAIN rather than carry on?

    Measured on a savings booklet: two allocation grids on facing pages, one
    per risk profile, with the same header, the same five columns and the same
    left edge. Every geometric test said continuation, and they were merged
    into one 58-row table whose rows then answered for the wrong profile.

    The tell is in the data: both start at "R - 47 ans". A table continuing
    onto the next page picks up where it left off; it never repeats the row it
    opened with."""
    if len(top) < 2 or len(nxt) < 2:
        return False
    # not the whole row — the VALUES differ, that is the whole point (64,00 %
    # against 44,00 % for the two profiles). What repeats is the LABEL.
    if _norm_row(top[0]) != _norm_row(nxt[0]):
        return False                      # no repeated header: nothing to tell
    opening = _row_label(top[1])
    return bool(opening) and opening == _row_label(nxt[1])


def _row_label(row: list) -> str:
    for cell in row:
        text = " ".join(str(cell or "").split()).lower()
        if text:
            return text
    return ""


def merge_cross_page_tables(pages: list[PageLayout]) -> None:
    """Mutates `pages`: continuation fragments are absorbed into the table on
    the page where it starts. Iterates last-to-first so a table spanning three
    pages chains naturally (5→4 first, then the merged 4 into 3)."""
    from tablerag.ingestion.imaging import stitch_vertical

    for i in range(len(pages) - 2, -1, -1):
        cur, nxt = pages[i], pages[i + 1]
        if cur.is_scan or nxt.is_scan:
            continue
        cur_tables = [r for r in cur.regions if r.type == "table"]
        nxt_tables = [r for r in nxt.regions if r.type == "table"]
        if not cur_tables or not nxt_tables:
            continue
        last = max(cur_tables, key=lambda r: r.bbox[3])
        first = min(nxt_tables, key=lambda r: r.bbox[1])
        if not _tables_continue(last, cur.height, first, nxt.height):
            continue
        last.grid = merge_grids(last.grid, first.grid)
        last.complex = table_grid_is_complex(last.grid)
        if last.crop_png and first.crop_png:
            last.crop_png = stitch_vertical(last.crop_png, first.crop_png)
        last.span_pages = [nxt.page] + first.span_pages
        nxt.regions.remove(first)


def analyze_document(pdf_bytes: bytes, dpi: int, min_chars: int,
                     table_dpi: int = 240) -> list[PageLayout]:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise PdfError(f"The file could not be opened as a PDF ({e}).") from e
    with doc:
        if doc.page_count == 0:
            raise PdfError("The PDF contains no pages.")
        pages = [analyze_page(page, dpi, min_chars, table_dpi) for page in doc]
    merge_cross_page_tables(pages)
    return pages


def crop_region_png(page_png: bytes, page_width: float,
                    bbox: tuple[float, float, float, float], pad: float = 6.0) -> bytes:
    """Crop a region (PDF-point bbox) out of the rendered page PNG."""
    with Image.open(io.BytesIO(page_png)) as img:
        scale = img.width / page_width
        x0 = max(0, int((bbox[0] - pad) * scale))
        y0 = max(0, int((bbox[1] - pad) * scale))
        x1 = min(img.width, int((bbox[2] + pad) * scale))
        y1 = min(img.height, int((bbox[3] + pad) * scale))
        if x1 <= x0 or y1 <= y0:
            return page_png
        out = io.BytesIO()
        img.crop((x0, y0, x1, y1)).save(out, format="PNG")
        return out.getvalue()
