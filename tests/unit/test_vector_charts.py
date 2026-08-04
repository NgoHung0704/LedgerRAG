"""Charts drawn as vector paths.

A chart emitted by PowerPoint or Excel is not an image block, so the figure
rule never saw it — and its labels are often OUTLINED, so its numbers are in no
text layer either. Measured on a fund factsheet: three pages, 0 image blocks,
652 vector paths, and about fifty values that ingestion simply lost.

Detecting them is half the job. The other half is that a vector chart's bars
have exact coordinates, so the numbers a model claims to have read off it can
be CHECKED — the only deterministic signal available for a picture.
"""

import fitz
import pytest

from tablerag.ingestion.chart_check import (
    agreement,
    chart_bars,
    read_numbers,
    varies,
)
from tablerag.ingestion.layout import (
    detect_vector_figures,
    looks_like_table_striping,
)


def bar_chart_pdf(values, *, gridlines=6, x0=80.0, base=400.0, scale=2.0):
    """A column chart the way Office emits one: vector rects on a baseline.

    Bars are drawn close enough to cluster — a real chart's columns nearly
    touch, and spacing them out only tests the clustering constant."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=500)
    for i in range(gridlines):
        y = base - i * 30
        page.draw_line(fitz.Point(60, y), fitz.Point(360, y), width=0.4)
    for i, value in enumerate(values):
        x = x0 + i * 28
        page.draw_rect(fitz.Rect(x, base - value * scale, x + 24, base),
                       color=None, fill=(0.1, 0.5, 0.7))
    data = doc.tobytes()
    doc.close()
    return fitz.open(stream=data, filetype="pdf")[0]


# --- detection -------------------------------------------------------------

def test_a_vector_chart_is_found_even_though_it_is_not_an_image():
    page = bar_chart_pdf([10, 25, 40, 15, 30])
    assert sum(1 for b in page.get_text("blocks") if b[6] == 1) == 0, \
        "precondition: nothing here is an image block"
    figures = detect_vector_figures(page, [])
    assert len(figures) == 1
    assert figures[0].type == "figure" and figures[0].vector is True


def test_a_detected_chart_carries_its_measured_bars():
    page = bar_chart_pdf([10, 25, 40, 15, 30])
    assert len(detect_vector_figures(page, [])[0].bars) == 5


def test_a_table_that_coincides_with_the_cluster_is_not_a_figure():
    """A bordered table is a cluster of paths too, and it is already an
    element — describing its picture would index it twice."""
    page = bar_chart_pdf([10, 25, 40, 15, 30])
    box = fitz.Rect(detect_vector_figures(page, [])[0].bbox)
    assert detect_vector_figures(page, [box]) == []


def test_a_page_wide_bogus_table_does_not_swallow_the_charts_under_it():
    """find_tables returns a region covering most of the page on the factsheet
    this was built from. Vetoing on overlap let that hide every chart, so the
    test is coincidence: the table must BE the cluster."""
    page = bar_chart_pdf([10, 25, 40, 15, 30])
    whole_page = fitz.Rect(0, 0, 400, 500)
    assert len(detect_vector_figures(page, [whole_page])) == 1


@pytest.mark.parametrize("heights,striping", [
    ([13.2, 13.2, 13.2, 13.2, 13.2], True),        # table row bands
    ([15.5, 13.2, 13.2, 13.2, 13.2], True),        # ... with a taller header
    ([4.0, 12.0, 30.0, 8.0, 21.0], False),         # bars
])
def test_table_row_bands_are_not_a_figure(heights, striping):
    rects = [fitz.Rect(10, 10 + i * 20, 120, 10 + i * 20 + h)
             for i, h in enumerate(heights)]
    assert looks_like_table_striping(rects) is striping


def test_hairlines_are_not_row_bands():
    """A line chart's gridlines are perfectly uniform; testing them as bands
    threw the whole chart away."""
    rules = [fitz.Rect(10, 10 + i * 20, 300, 10 + i * 20 + 0.4)
             for i in range(8)]
    assert looks_like_table_striping(rules) is False


# --- measuring the bars ----------------------------------------------------

def test_bars_are_measured_from_the_shared_baseline():
    page = bar_chart_pdf([10, 25, 40, 15, 30])
    bars = sorted(chart_bars(page, (0, 0, 400, 500)))
    assert len(bars) == 5
    # proportional to the values, whatever the absolute scale
    k = bars[0] / 10
    assert all(abs(b / k - v) < 0.1 for b, v in zip(bars, sorted([10, 25, 40, 15, 30])))


def test_gridlines_are_not_mistaken_for_bars():
    """They share an edge like bars do, but they are all the same length. On
    the factsheet this returned 5, 10 and 11 phantom "bars"."""
    assert varies([7.5] * 11) is False
    assert varies([4.0, 12.0, 30.0]) is True


# --- reading the numbers a model claims -----------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Le secteur Industries est à 27,6 et Santé à 14,6", [27.6, 14.6]),
    ("81.5% cycliques, 3.3% pétrolières", [81.5, 3.3]),
    ("un actif de 2 000 millions", [2000.0]),
])
def test_numbers_are_read_in_french_notation(text, expected):
    assert read_numbers(text) == expected


# --- the check itself ------------------------------------------------------

# the sectorielle chart of the factsheet this was built from: the values it
# prints, and bars drawn to one scale (2.2585 pt per point of percentage,
# measured from the PDF) with the rounding a real drawing carries
TRUE_VALUES = [0.8, 11.9, 8.3, 27.6, 18.2, 11.9, 15.3, 10.8, 13.1, 4.5, 2.1,
               16.5, 7.5, 14.6, 3.7, 16.0, 8.0, 3.1]
BARS = [round(v * 2.2585, 2) for v in TRUE_VALUES]


def test_a_correct_reading_agrees_with_the_bars():
    score, note = agreement(BARS, TRUE_VALUES)
    assert score > 0.99, note


@pytest.mark.parametrize("corruption,label", [
    ([61.5 if v == 16.5 else v for v in TRUE_VALUES], "a transposed digit"),
    (TRUE_VALUES + [42.0], "an invented value"),
])
def test_a_corrupted_reading_disagrees_loudly(corruption, label):
    score, _ = agreement(BARS, corruption)
    assert score < 0.9, f"{label} should not pass"


def test_missing_values_are_a_failure_not_a_pass():
    score, note = agreement(BARS, TRUE_VALUES[:-1])
    assert score == 0.0
    assert "more bars than numbers" in note


@pytest.mark.parametrize("bars", [[], [5.0, 9.0]])
def test_an_unmeasurable_figure_is_not_checked_rather_than_failed(bars):
    """None means NOT CHECKED. Scoring a doughnut or a line chart zero would
    fill Review with figures no reviewer can do anything about."""
    score, note = agreement(bars, [10.0, 20.0])
    assert score is None
    assert "not checked" in note
