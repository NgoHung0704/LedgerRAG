"""Check what a model read off a chart against the chart's own geometry.

A vector chart's bars are rectangles with exact coordinates. The values printed
on them are usually outlined text, so only a VLM can read them — but the bars
themselves are measurable, and a set of correctly read values must be
proportional to the bars that carry them.

That gives a deterministic confidence signal for something otherwise
unverifiable. Measured on a fund factsheet: with the labels read correctly the
worst disagreement was 0.05 of a percentage point; with one bar mispaired it
was 22. There is no middle ground to be ambiguous about.

The comparison is PAIRING-FREE — both sides are sorted before fitting — because
which printed number belongs to which bar is exactly what cannot be recovered
from prose.
"""

from __future__ import annotations

import re

import fitz

# hairlines are gridlines and axes; the plot frame is not a bar either
# 0.8, not more: a bar for a value of 0,2 is under a point tall, and dropping
# it cost two whole categories on the factsheet's geographic chart — with this
# the measured group pattern matches the drawing exactly on both its charts.
_MIN_BAR_SIDE = 0.8
_MAX_BAR_SHARE = 0.9      # a rect filling the plot is its background
_BASELINE_TOL = 1.0       # points; bars on the same axis line up this closely
_RULE_MAJORITY = 0.5      # this share sharing one length = rules, not bars
# the tallest bar carries one of the largest values read — try each in turn
# rather than assuming which, and keep the scale that explains the most bars
_SCALE_CANDIDATES = 3
_MATCH_TOLERANCE = 0.02   # of the largest value read
# bars of one category touch; the gap to the next category is wider than a bar
_GROUP_GUTTER = 1.6
# a number as printed on a French chart: 27,6 · 1 234,5 · 81.5%
# the integer part is unbounded on purpose: \d{1,3} was meant for grouped
# thousands, but it chopped a bare year into "202" and "1", which turned a
# description that correctly refused to state any value into twelve phantoms
_NUMBER = re.compile(r"-?\d+(?:[  ]\d{3})*(?:[.,]\d+)?")


def read_numbers(text: str) -> list[float]:
    """Every number in a description, as floats. Deliberately greedy: the
    check only needs the SET of values the model claims to have read."""
    out = []
    for raw in _NUMBER.findall(text or ""):
        try:
            out.append(float(raw.replace(" ", "").replace(" ", "")
                             .replace(",", ".")))
        except ValueError:
            continue
    return out


def duplicates_page_text(description: str, page_text: str) -> bool:
    """Does this description carry no number the page's text does not already?

    A title banner holds the document's name and date, so a model calls it
    informative — reasonably, it IS information. But that text is real text on
    the page and already indexed, so describing it stores the same words a
    second time, and in a corpus of near-identical factsheets those copies
    compete with each other in retrieval.

    Telling the model this in the prompt was tried and measured: it did not
    change the judgement, and it made every description more verbose — the
    numbers read off one chart went from 5 stray to 29, and the geometric
    agreement on another fell from 0.91 to 0.82. So the rule lives here, where
    it is deterministic and costs the model nothing. It is the same test
    layout.duplicates_table_text already applies to text blocks.

    Numbers, not words: "orange", "banner" and "logo" are the model's own
    vocabulary and appear nowhere on the page, while the facts a figure is
    worth indexing for are its figures. A description with no numbers at all
    is left to the model's own judgement.
    """
    numbers = set(read_numbers(description))
    if not numbers:
        return False
    return numbers <= set(read_numbers(page_text))


def index_verdict(description: str, informative: bool,
                  page_text: str) -> str | None:
    """Should this figure's description go into the index? None means yes;
    otherwise the reason it is held out.

    Both the ingest path and the eval gate ask THIS, not the model's flag on
    its own. The gate first graded the raw flag and reported the banner as a
    miss after the pipeline had already learnt to hold it back — a gate that
    scores an intermediate result cannot tell you what the system does.
    """
    if not informative:
        return "decorative"
    if duplicates_page_text(description, page_text):
        return "duplicate"
    return None


def _bars(page: fitz.Page, bbox: tuple[float, float, float, float]
          ) -> tuple[list[fitz.Rect], bool]:
    """The bars inside `bbox`, and whether the chart runs in columns.

    Bars are identified by the one property that defines them: they all grow
    from the SAME baseline. Colour does not identify them — tick marks and
    label backgrounds outnumbered the bars 40 to 18 on the chart this was
    built from — and a grouped chart's two colours share one scale anyway, so
    both series belong to the same comparison.

    Both orientations are tried: a column chart shares a bottom edge and
    carries its value in the height, a horizontal bar chart shares a left edge
    and carries it in the width."""
    box = fitz.Rect(bbox)
    plot_area = box.get_area()
    candidates = []
    for drawing in page.get_drawings():
        if not drawing.get("fill"):
            continue
        rect = fitz.Rect(drawing["rect"])
        if not box.contains(rect):
            continue
        if rect.width < _MIN_BAR_SIDE or rect.height < _MIN_BAR_SIDE:
            continue                                   # gridline / axis
        if rect.get_area() > _MAX_BAR_SHARE * plot_area:
            continue                                   # plot background
        candidates.append(rect)

    def on_shared_edge(edge) -> list[fitz.Rect]:
        tally: dict[int, list[fitz.Rect]] = {}
        for rect in candidates:
            tally.setdefault(round(edge(rect) / _BASELINE_TOL), []).append(rect)
        return max(tally.values(), key=len) if tally else []

    columns = on_shared_edge(lambda r: r.y1)
    horizontal = on_shared_edge(lambda r: r.x0)
    if len(columns) >= len(horizontal):
        return (columns, True) if varies([r.height for r in columns]) else ([], True)
    return (horizontal, False) if varies([r.width for r in horizontal]) else ([], False)


def chart_bars(page: fitz.Page,
               bbox: tuple[float, float, float, float]) -> list[float]:
    """Lengths of the bars inside `bbox` — what carries their value."""
    rects, vertical = _bars(page, bbox)
    return [(r.height if vertical else r.width) for r in rects]


def bar_groups(page: fitz.Page,
               bbox: tuple[float, float, float, float]) -> list[int]:
    """How many bars sit under each category, in order.

    This is the error a reader never makes and a model does: on the factsheet,
    two sectors carry only the index bar, and the VLM — reading a row of values
    without knowing a slot held one — slid every later value one sector along.
    Every number it read was RIGHT; from "Santé" on, all of them landed on the
    wrong sector.

    A pairing-free check cannot see that at all — the multiset of values is
    identical either way — so the geometry is handed to the model as evidence
    instead, the way a table's text-layer grid already is."""
    rects, vertical = _bars(page, bbox)
    if len(rects) < 3:
        return []
    thickness = [(r.width if vertical else r.height) for r in rects]
    gutter = (sum(thickness) / len(thickness)) * _GROUP_GUTTER
    positions = sorted((r.x0 + r.x1) / 2 if vertical else (r.y0 + r.y1) / 2
                       for r in rects)
    groups, run = [], 1
    for previous, position in zip(positions, positions[1:]):
        if position - previous > gutter:
            groups.append(run)
            run = 1
        else:
            run += 1
    groups.append(run)
    return groups


def varies(lengths: list[float]) -> bool:
    """Are these bars, or a set of rules?

    A line chart's gridlines and a horizontal chart's axis ticks also share an
    edge, and on the factsheet they came back as 5, 10 and 11 "bars" — all
    exactly the same length. Bars differ; that is what a bar chart is. Measured
    there: real series spread 36x, rule sets spread 1.00x.
    """
    if len(lengths) < 3:
        return False
    tally: dict[int, int] = {}
    for length in lengths:
        key = round(length / _BASELINE_TOL)
        tally[key] = tally.get(key, 0) + 1
    return max(tally.values()) / len(lengths) < _RULE_MAJORITY


def agreement(heights: list[float],
              values: list[float]) -> tuple[float | None, str]:
    """How well one linear scale explains the bars, given the read values.

    Returns (agreement in 0..1, note), or (None, why) when there is nothing to
    compare — a doughnut, a line chart, a picture. None means NOT CHECKED and
    must not be read as a bad score: flagging every unmeasurable figure would
    fill Review with things no reviewer can act on.

    Both sides are sorted: which printed number belongs to which bar is not
    recoverable from a prose description, and a correct reading is proportional
    whichever way it is ordered.
    """
    bars = sorted(h for h in heights if h > 0)
    reads = sorted(v for v in values if v > 0)
    if len(bars) < 3:
        return None, "no measurable bar series — not checked"
    if len(reads) < len(bars):
        return 0.0, (f"read {len(reads)} values for {len(bars)} bars — "
                     "the chart has more bars than numbers were read")

    # Every bar must find a value; leftover values are EXPECTED and ignored.
    # A description mentions the axis ("from 0% to 28%") and its legend, and
    # those numbers are not bars. Discarding the extras by size was wrong and
    # measured wrong: the axis maximum outranks every bar but the tallest, so
    # it survived while the smallest real bar was thrown away — a perfect
    # reading of a factsheet chart scored 0.76 instead of 0.998.
    best_score, best_note = 0.0, "no scale fits the bars"
    for candidate in reads[-_SCALE_CANDIDATES:]:
        scale = bars[-1] / candidate
        if scale <= 0:
            continue
        matched, worst, free = 0, 0.0, list(reads)
        tolerance = _MATCH_TOLERANCE * max(reads)
        for bar in bars:
            wanted = bar / scale
            near = min(free, key=lambda v: abs(v - wanted), default=None)
            if near is None or abs(near - wanted) > tolerance:
                continue
            free.remove(near)
            worst = max(worst, abs(near - wanted))
            matched += 1
        score = matched / len(bars)
        if score > best_score:
            best_score, best_note = score, (
                f"{matched}/{len(bars)} bars matched a value read from them, "
                f"worst disagreement {worst:.2f}"
                + (f"; {len(free)} number(s) read that no bar carries"
                   if free else ""))
    return best_score, best_note
