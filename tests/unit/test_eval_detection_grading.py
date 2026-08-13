"""The detection gate grades REACHABILITY, not a count.

`make eval-tables` reads tables that were already cropped for it, so a detector
that misses the main table of every document still scores 88.4 %. Measured on
the box: EPSENS DEFIS had one table element in the whole file, and the value
50,46 existed nowhere but page prose - so every retrieval fix was powerless on
the question that asked for it.
"""

import importlib.util
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location(
        "run_eval_detection",
        REPO / "tests" / "eval" / "tables" / "run_eval_detection.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PERF = [["Performances cumulées", "5 ans", "10 ans"],
        ["Portefeuille", "50,46", "148,90"]]
RISK = [["Volatilité", "1 an", "3 ans"], ["Portefeuille", "8,11", "10,72"]]


def test_a_value_inside_an_accepted_grid_is_reachable(gate):
    assert gate.reachable([PERF], "50,46")


def test_a_value_on_the_page_but_in_no_grid_is_not(gate):
    # exactly the DEFIS case: the risk table was detected, the performance
    # tables were not, and 50,46 was left in prose
    assert not gate.reachable([RISK], "50,46")


def test_spacing_introduced_by_extraction_is_not_read_as_a_miss(gate):
    assert gate.reachable([[["50, 46"]]], "50,46")


def test_a_page_fails_when_any_expected_value_is_unreachable(gate):
    item = {"tables": 3, "must_reach": ["50,46", "9,55"]}
    ok, detail = gate.grade(item, [PERF])
    assert not ok
    assert "9,55" in detail


def test_a_page_passes_only_when_every_value_is_reachable(gate):
    item = {"tables": 2, "must_reach": ["50,46", "10,72"]}
    ok, _ = gate.grade(item, [PERF, RISK])
    assert ok


def test_the_right_count_with_the_wrong_content_still_fails(gate):
    # three detections that happen to be the page banner, a chart legend and a
    # risk table is not three tables found
    item = {"tables": 3, "must_reach": ["50,46"]}
    ok, _ = gate.grade(item, [RISK, RISK, RISK])
    assert not ok, "counting detections is not the same as finding the table"
