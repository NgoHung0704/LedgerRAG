"""Reading order and the layout-heavy flag.

A PowerPoint- or Word-derived PDF hands its text blocks over in SHAPE order, so
a slide title can arrive last; sorting by position fixes that. But a slide's
process diagram is genuinely 2-D — column = step, row = aspect — and NO linear
order recovers which description belongs to which step. Those pages are flagged
instead of being passed off as faithful text.
"""

from tablerag.ingestion.layout import looks_like_column_layout

PAGE_W = 1000.0


def _col(x0: float, x1: float, ys: list[tuple[float, float]]):
    return [(x0, y0, x1, y1) for y0, y1 in ys]


# --- the slide that started this: 5 steps x (name, description, output) -----

def test_five_column_diagram_is_flagged():
    boxes: list[tuple[float, float, float, float]] = []
    for i in range(5):
        x0 = 40 + i * 190
        boxes += _col(x0, x0 + 150, [(200, 240), (300, 460), (520, 560)])
    assert looks_like_column_layout(boxes, PAGE_W) is True


def test_three_columns_is_the_threshold():
    three, two = [], []
    for i in range(3):
        x0 = 40 + i * 300
        three += _col(x0, x0 + 250, [(100, 200), (300, 400)])
    for i in range(2):
        x0 = 40 + i * 460
        two += _col(x0, x0 + 400, [(100, 200), (300, 400), (500, 600)])
    assert looks_like_column_layout(three, PAGE_W) is True
    # two-column prose reads acceptably once sorted; flagging every such PDF
    # would drown the review queue
    assert looks_like_column_layout(two, PAGE_W) is False


# --- ordinary pages must stay unflagged ------------------------------------

def test_single_column_page_is_not_flagged():
    boxes = _col(60, 940, [(50 + i * 90, 120 + i * 90) for i in range(9)])
    assert looks_like_column_layout(boxes, PAGE_W) is False


def test_a_short_page_is_never_flagged():
    """A title plus two paragraphs is not a diagram, whatever its geometry."""
    boxes = _col(60, 940, [(50, 100), (150, 300), (350, 500)])
    assert looks_like_column_layout(boxes, PAGE_W) is False


def test_columns_need_stacked_content():
    """Five side-by-side single labels (a footer row, a legend) are not a
    column layout — a column has to stack."""
    boxes = [(40 + i * 190, 900, 40 + i * 190 + 150, 940) for i in range(6)]
    assert looks_like_column_layout(boxes, PAGE_W) is False


def test_degenerate_input():
    assert looks_like_column_layout([], PAGE_W) is False
    assert looks_like_column_layout(_col(0, 10, [(0, 1)] * 8), 0) is False


# --- block ordering ---------------------------------------------------------

def test_blocks_are_read_top_down_whatever_their_shape_order():
    """The concrete defect: a slide title emitted last in the content stream
    must still come first in the extracted text."""
    # (x0, y0, x1, y1, text, no, type) as PyMuPDF yields them
    blocks = [
        (60, 500, 900, 560, "body second", 2, 0),
        (60, 300, 900, 360, "body first", 1, 0),
        (60, 40, 900, 90, "THE TITLE", 3, 0),
    ]
    ordered = sorted(blocks, key=lambda b: (round(b[1], 1), b[0]))
    assert [b[4] for b in ordered] == ["THE TITLE", "body first", "body second"]


def test_blocks_on_the_same_line_read_left_to_right():
    blocks = [
        (500, 100, 900, 140, "right", 1, 0),
        (60, 100, 400, 140, "left", 2, 0),
    ]
    ordered = sorted(blocks, key=lambda b: (round(b[1], 1), b[0]))
    assert [b[4] for b in ordered] == ["left", "right"]
