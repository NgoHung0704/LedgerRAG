"""VLM table-region detection: box parsing/validation + fractional crop.
This is the scanned-multi-table fix (find_tables can't see scans)."""

import io

from PIL import Image

from tablerag.ingestion.imaging import crop_fraction
from tablerag.ingestion.table_pipeline import parse_region_boxes


def test_parse_two_regions():
    text = ('Here are the tables: '
            '[{"x0":0.08,"y0":0.10,"x1":0.92,"y1":0.34},'
            '{"x0":0.08,"y0":0.55,"x1":0.92,"y1":0.71}]')
    boxes = parse_region_boxes(text)
    assert len(boxes) == 2
    assert boxes[0][1] < boxes[1][1]  # sorted top-to-bottom


def test_parse_empty_and_junk():
    assert parse_region_boxes("[]") == []
    assert parse_region_boxes("no json here") == []
    assert parse_region_boxes("[not valid json") == []


def test_parse_clamps_and_orders_coords():
    boxes = parse_region_boxes('[{"x0":1.2,"y0":0.9,"x1":-0.1,"y1":0.2}]')
    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0]
    assert 0.0 <= x0 < x1 <= 1.0
    assert 0.0 <= y0 < y1 <= 1.0


def test_parse_drops_degenerate_and_dupes():
    text = ('[{"x0":0.1,"y0":0.1,"x1":0.11,"y1":0.11},'   # too small
            '{"x0":0.1,"y0":0.3,"x1":0.9,"y1":0.5},'
            '{"x0":0.11,"y0":0.31,"x1":0.89,"y1":0.49}]')  # duplicate of #2
    boxes = parse_region_boxes(text)
    assert len(boxes) == 1


def test_parse_ignores_missing_keys():
    assert parse_region_boxes('[{"x0":0.1,"y0":0.1}]') == []


def test_crop_fraction_cuts_the_right_region():
    buf = io.BytesIO()
    Image.new("RGB", (1000, 800), "white").save(buf, format="PNG")
    out = crop_fraction(buf.getvalue(), (0.0, 0.5, 1.0, 1.0), pad=0.0)
    with Image.open(io.BytesIO(out)) as img:
        assert img.width == 1000
        assert 390 <= img.height <= 410  # bottom half (~400px)


def test_crop_fraction_bad_bytes_passthrough():
    assert crop_fraction(b"not an image", (0, 0, 1, 1)) == b"not an image"
