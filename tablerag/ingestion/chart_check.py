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
_MIN_BAR_SIDE = 1.5
_MAX_BAR_SHARE = 0.9      # a rect filling the plot is its background
_BASELINE_TOL = 1.0       # points; bars on the same axis line up this closely
_RULE_MAJORITY = 0.5      # this share sharing one length = rules, not bars
# a number as printed on a French chart: 27,6 · 1 234,5 · 81.5%
_NUMBER = re.compile(r"-?\d{1,3}(?:[  ]\d{3})*(?:[.,]\d+)?")


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


def chart_bars(page: fitz.Page,
               bbox: tuple[float, float, float, float]) -> list[float]:
    """Lengths of the bars inside `bbox`.

    Bars are identified by the one property that defines them: they all grow
    from the SAME baseline — the axis. Colour does not identify them (tick
    marks and label backgrounds outnumbered the bars 40 to 18 on the chart
    this was built from), and a grouped chart's two colours share one scale
    anyway, so both series belong in the same comparison.

    Both orientations are tried — a column chart shares a bottom edge and
    carries its value in the height, a horizontal bar chart shares a left edge
    and carries it in the width — and whichever finds more bars wins."""
    box = fitz.Rect(bbox)
    plot_area = box.get_area()
    rects = []
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
        rects.append(rect)

    def on_shared_edge(edge, length) -> list[float]:
        tally: dict[int, list[float]] = {}
        for rect in rects:
            key = round(edge(rect) / _BASELINE_TOL)
            tally.setdefault(key, []).append(length(rect))
        return max(tally.values(), key=len) if tally else []

    columns = on_shared_edge(lambda r: r.y1, lambda r: r.height)
    horizontal = on_shared_edge(lambda r: r.x0, lambda r: r.width)
    best = columns if len(columns) >= len(horizontal) else horizontal
    return best if varies(best) else []


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
    # more numbers than bars is normal: axis ticks and a legend are numbers
    # too. Take the largest ones, which is what the bars carry.
    reads = reads[-len(bars):]
    total_h, total_v = sum(bars), sum(reads)
    if total_v <= 0 or total_h <= 0:
        return None, "degenerate scale — not checked"
    scale = total_h / total_v
    span = max(reads)
    worst = max(abs(h / scale - v) for h, v in zip(bars, reads))
    return max(0.0, 1.0 - worst / span), (
        f"{len(bars)} bars, worst disagreement {worst:.2f} on a span of {span:g}")
