"""The grader must not punish the behaviour the product is asked for.

Graded as traps, the good answers scored FAIL: the trap grader passes only on a
refusal, so an answer that named each edition with its date - which is what
OVERLAP_RULE asks for - counted against the score. The metric fell while the
product improved, and a metric that moves the wrong way is worse than none.
"""

import importlib.util
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def harness():
    spec = importlib.util.spec_from_file_location(
        "run_eval_qa", REPO / "tests" / "eval" / "qa" / "run_eval_qa.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ITEM = {"type": "contrast",
        "expected_answer_contains": ["30/09/2021", "31/08/2023", "30/09/2024"]}
CITED = [{"filename": "x.pdf", "page": 1}]


def test_picking_one_edition_silently_fails(harness):
    ok, detail = harness.grade(
        ITEM, "La performance cumulée sur 5 ans est de 2,43 %.", CITED, None)
    assert not ok
    assert "without naming" in detail


def test_naming_two_editions_passes(harness):
    ok, _ = harness.grade(
        ITEM,
        "Elle est de 2,43 % au 30/09/2021 et de -10,35 % au 30/09/2024.",
        CITED, None)
    assert ok


def test_refusing_still_passes(harness):
    # refusing is not the best answer, but it is an honest one
    ok, detail = harness.grade(
        ITEM, "Les documents ne contiennent pas cette information.", CITED, None)
    assert ok
    assert "refused" in detail


def test_one_edition_named_is_not_enough(harness):
    # one date identifies a version; two identify a CHOICE, which is the point
    ok, _ = harness.grade(
        ITEM, "Au 30/09/2021 elle est de 2,43 %.", CITED, None)
    assert not ok
