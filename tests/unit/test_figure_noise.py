"""262 figures in one 24-page document, and three hours of VLM to describe them.

Measured on the box 2026-08-27. A 24-page procedure took 10 776 s to ingest and
produced no tables at all — the time was 262 figure descriptions, one VLM call
each. Two distinct causes, from the page distribution:

    page  1    : 16
    pages 3–7  : 22, 27, 34, 38, 28     ← 149 figures on five pages
    pages 14–24: 4, 4, 4, 4, …          ← a constant floor

The floor is page furniture: three boxes at identical coordinates on all 24
pages — a rule, a header block, a logo. The spike is one process diagram per
page, cut into twenty to thirty vector clusters, each described separately.

Neither is a figure a reader would point at, and 262 calls for one document is
a cost nothing bounds. The two functions here address the two causes; both are
pure so the thresholds can be argued about against numbers.
"""

import pytest

from tablerag.ingestion.layout import (
    PageLayout,
    Region,
    collapse_crowded_figures,
    repeated_figure_boxes,
)


def _fig(x0, y0, x1, y1):
    return Region(type="figure", bbox=(x0, y0, x1, y1))


def _page(n, regions):
    return PageLayout(page=n, width=595, height=842, image_png=b"", is_scan=False,
                      regions=regions)


# --- page furniture: the same box on page after page -----------------------

def test_a_box_on_every_page_is_furniture():
    logo = (444, 27, 557, 77)
    # the content figure moves down the page from one page to the next, as
    # content does — an earlier version of this test left it at fixed
    # coordinates, which made it furniture too and the assertion nonsense
    pages = [_page(n, [_fig(*logo), _fig(100, 300 + n, 300, 500 + n)])
             for n in range(1, 25)]
    assert repeated_figure_boxes(pages) == {logo}


def test_a_box_on_one_page_is_content():
    pages = [_page(1, [_fig(100, 300, 300, 500)]),
             _page(2, [_fig(50, 50, 200, 200)])]
    assert repeated_figure_boxes(pages) == set()


def test_a_box_that_shifts_a_fraction_of_a_point_still_counts():
    # a header logo is placed by the template, but coordinates come back with
    # sub-point noise; exact equality would miss every real case. Noise, not
    # drift: an earlier version accumulated 0.2pt per page and demanded the
    # tolerance absorb 4.8pt across the document, which no template does.
    jitter = [0.0, 0.3, -0.2, 0.4, -0.4]
    pages = [_page(n, [_fig(444 + jitter[n % 5], 27, 557 + jitter[n % 5], 77)])
             for n in range(1, 25)]
    assert len(repeated_figure_boxes(pages)) == 1


def test_a_figure_that_drifts_down_the_document_is_not_furniture():
    """The bug this file's first version shipped with.

    A picture moving a point per page put three consecutive pages in one
    quantisation bucket, "appears on three pages" was satisfied, and a real
    figure was deleted as a logo. Asking for a SHARE of the document instead of
    a count cannot be fooled that way: the drifting figure never reaches half
    the pages in any one bucket, while a template element is on all of them.
    """
    pages = [_page(n, [_fig(100, 300 + n, 300, 500 + n)]) for n in range(1, 25)]
    assert repeated_figure_boxes(pages) == set()


def test_a_figure_repeated_on_a_few_pages_of_many_is_not_furniture():
    """What the SHARE threshold buys, as distinct from the tolerance.

    A chapter divider, a recurring illustration: the same picture in the same
    place on three pages of twenty-four. A fixed count of three deletes it. A
    share does not — furniture is on the whole document, not on an eighth of
    it. Written after a break test showed the drift case above was carried by
    the tolerance alone and said nothing about this threshold.
    """
    divider = (100, 300, 300, 500)
    pages = [_page(n, [_fig(*divider)] if n in (5, 11, 17) else [])
             for n in range(1, 25)]
    assert repeated_figure_boxes(pages) == set()


def test_two_pages_are_not_enough_to_call_it_furniture():
    # a figure repeated on a spread is a figure, not a template element
    pages = [_page(n, [_fig(100, 300, 300, 500)]) for n in range(1, 3)]
    assert repeated_figure_boxes(pages) == set()


def test_only_figures_are_considered():
    # a table in the same place on every page is a cross-page table, and
    # dropping it would delete the thing this product exists for
    box = (50, 50, 500, 700)
    pages = [_page(n, [Region(type="table", bbox=box)]) for n in range(1, 25)]
    assert repeated_figure_boxes(pages) == set()


def test_a_short_document_has_no_furniture_to_find():
    assert repeated_figure_boxes([]) == set()


# --- a crowded page is one diagram, not thirty figures ---------------------

def test_a_crowded_page_becomes_a_single_region():
    crowded = [_fig(10 * i, 10 * i, 10 * i + 60, 10 * i + 40) for i in range(30)]
    out = collapse_crowded_figures(crowded, limit=14)
    assert len(out) == 1


def test_the_collapsed_region_covers_all_of_them():
    crowded = [_fig(100, 100, 160, 140), _fig(400, 500, 460, 540)]
    out = collapse_crowded_figures(crowded, limit=1)
    assert out[0].bbox == (100, 100, 460, 540)


def test_an_ordinary_page_is_left_exactly_alone():
    figures = [_fig(100, 100, 300, 300), _fig(100, 400, 300, 600)]
    assert collapse_crowded_figures(figures, limit=14) == figures


def test_the_limit_is_inclusive():
    # exactly at the limit is still an ordinary page; the spike started well
    # above it, so the boundary belongs on the permissive side
    figures = [_fig(i, i, i + 60, i + 40) for i in range(14)]
    assert collapse_crowded_figures(figures, limit=14) == figures


def test_the_collapsed_region_says_it_is_a_diagram_not_a_picture():
    # a reader has to be able to tell this apart from a figure the detector
    # found cleanly, and so does anyone reading the review queue
    out = collapse_crowded_figures([_fig(i, i, i + 60, i + 40) for i in range(30)],
                                   limit=14)
    assert out[0].layout_suspect is True


def test_nothing_in_nothing_out():
    assert collapse_crowded_figures([], limit=14) == []


@pytest.mark.parametrize("count,expected", [(0, 0), (14, 14), (15, 1), (38, 1)])
def test_the_measured_distribution(count, expected):
    """The real page counts: 4 and 12 pass through, 16 and 38 collapse."""
    figures = [_fig(i, i, i + 60, i + 40) for i in range(count)]
    assert len(collapse_crowded_figures(figures, limit=14)) == expected
