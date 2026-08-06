"""Lint for the eval-qa question sets.

A malformed dataset does not crash — it makes the GATE LIE, which is worse: the
run reports FAIL and the pipeline gets blamed for a typo in the expectations.
Every rule here comes from a way an eval file has actually been written wrong.

The grader (`run_eval_qa.grade`) requires EVERY entry of
`expected_answer_contains`, and treats "|" inside one entry as acceptable
alternatives. Writing alternatives as separate list entries therefore demands
that the answer contain all spellings at once — a guaranteed failure.
"""

import json
import re
import sys
from pathlib import Path

import pytest

QA = Path(__file__).resolve().parents[1] / "eval" / "qa"
sys.path.insert(0, str(QA))

from run_eval_qa import _norm  # noqa: E402

DATASETS = sorted(QA.glob("*.jsonl"))
TYPES = {"table", "text", "factual", "trap", "figure"}
# UTF-8 bytes decoded as latin-1/cp1252: "é" -> "Ã©", "€" -> "â¬". A whole
# dataset arrived like this once; the questions reach the API as garbage
# French and no expected string can ever match.
MOJIBAKE = re.compile(r"Ã.|â[-¿]|Â[ -¿]")


def items(path: Path) -> list[dict]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def graded(path: Path) -> list[dict]:
    """Flat list of everything grade() will see — a followups line is a
    conversation whose turns carry the expectations."""
    out = []
    for item in items(path):
        if "turns" in item:
            out += [{**t, "id": f"{item['id']}:{i}"}
                    for i, t in enumerate(item["turns"]) if "type" in t]
        elif "expected_kbs" not in item:  # routing.jsonl scores the router
            out.append(item)
    return out


@pytest.mark.parametrize("path", DATASETS, ids=lambda p: p.name)
def test_dataset_is_utf8_and_parses(path):
    assert items(path), f"{path.name} is empty"
    text = path.read_text(encoding="utf-8")
    found = MOJIBAKE.findall(text)
    assert not found, (
        f"{path.name} looks like UTF-8 decoded as latin-1 ({found[:5]}). "
        "Re-save it as UTF-8 — accented French will not match otherwise.")


@pytest.mark.parametrize("path", DATASETS, ids=lambda p: p.name)
def test_ids_are_unique(path):
    ids = [i["id"] for i in items(path)]
    assert len(ids) == len(set(ids)), f"{path.name}: duplicate ids"


@pytest.mark.parametrize("path", DATASETS, ids=lambda p: p.name)
def test_expectations_are_well_formed(path):
    for item in graded(path):
        where = f"{path.name} {item['id']}"
        assert item["type"] in TYPES, f"{where}: unknown type {item['type']!r}"
        expected = item.get("expected_answer_contains", [])

        if item["type"] == "figure":
            # a retrieval question: the assistant is not asked to read the
            # picture, so there is no content to expect — only a source, and a
            # page, because "the right document" is not the same as "the right
            # chart" in a fourteen-page booklet
            assert not expected, (
                f"{where}: a figure question grades retrieval, not content — "
                "expected_answer_contains is never read")
            assert item.get("expected_doc"), f"{where}: no expected_doc"
            assert item.get("expected_page"), f"{where}: no expected_page"
            continue

        if item["type"] == "trap":
            # traps pass on refusal / no citation / verifier warning; an
            # expectation or an expected_doc is never read and only misleads
            assert not expected, f"{where}: a trap must not expect content"
            assert "expected_doc" not in item, (
                f"{where}: expected_doc is ignored for traps — drop it")
            continue

        assert expected, f"{where}: nothing expected, so it cannot fail"
        assert item.get("expected_doc"), f"{where}: no expected_doc"


@pytest.mark.parametrize("path", DATASETS, ids=lambda p: p.name)
def test_alternatives_are_not_written_as_separate_entries(path):
    """["1er janvier 2027", "2027"] demands BOTH — but one contains the other,
    so the author meant "either". Redundant conjuncts can only make the gate
    stricter than intended."""
    for item in graded(path):
        entries = [_norm(e) for e in item.get("expected_answer_contains", [])]
        for i, a in enumerate(entries):
            for j, b in enumerate(entries):
                if i != j and "|" not in a and "|" not in b and a in b:
                    assert False, (
                        f"{path.name} {item['id']}: {a!r} is contained in "
                        f"{b!r} — join them with '|' if they are alternatives")


@pytest.mark.parametrize("path", DATASETS, ids=lambda p: p.name)
def test_percentages_allow_the_french_spacing(path):
    """French typography puts a thin space before "%", so a model writing
    "20 %" fails an expectation of "20%" while being perfectly right."""
    for item in graded(path):
        for entry in item.get("expected_answer_contains", []):
            variants = entry.split("|")
            tight = [v for v in variants if re.search(r"\d%", v)]
            spaced = [v for v in variants if re.search(r"\d\s%", v)]
            if tight and not spaced:
                assert False, (
                    f"{path.name} {item['id']}: {entry!r} only accepts "
                    f"{tight[0]!r}; add the spaced form too (e.g. "
                    f"'{tight[0]}|{tight[0].replace('%', ' %')}')")
