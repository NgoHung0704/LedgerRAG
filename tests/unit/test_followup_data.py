"""Structural guard for the multi-turn eval set (tests/eval/qa/followups.jsonl).

The follow-up gate runs against a live stack, so it can't run in CI — but a
malformed conversation (a follow-up with no expectation, a typo'd source) would
silently score nothing. These offline checks keep the data honest, and smoke-
test that the runner's grader is wired to the eval-qa grader."""

import json
import sys
from pathlib import Path

import pytest

QA_DIR = Path(__file__).resolve().parents[1] / "eval" / "qa"
sys.path.insert(0, str(QA_DIR))

FOLLOWUPS = QA_DIR / "followups.jsonl"
KNOWN_DOCS = {
    "Cotation emplois CETIAT 2023_07_27.pdf",
    "Avenant du 11 juillet 2023.pdf",
    "Glossaire-Classification.pdf",
}


def _convos():
    return [json.loads(line) for line in
            FOLLOWUPS.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_file_parses_and_ids_unique():
    convos = _convos()
    assert convos, "followups.jsonl is empty"
    ids = [c["id"] for c in convos]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


@pytest.mark.parametrize("convo", _convos(), ids=lambda c: c["id"])
def test_conversation_shape(convo):
    turns = convo["turns"]
    assert len(turns) >= 2, "a follow-up conversation needs an opener + a follow-up"

    graded = [t for t in turns if t.get("expected_answer_contains")]
    assert graded, "no graded turn — the follow-up must carry expectations"
    # the opener sets context; only later turns are graded
    assert not turns[0].get("expected_answer_contains"), \
        "the first turn is context-setting and must not be graded"

    for t in graded:
        assert t.get("expected_doc") in KNOWN_DOCS, \
            f"unknown/typo'd expected_doc: {t.get('expected_doc')!r}"
        # the whole point: a graded follow-up is a FRAGMENT that leans on the
        # thread — shorter than the opener it follows
        assert len(t["question"]) < len(turns[0]["question"]), \
            "follow-up should be a fragment shorter than the opening question"


def test_runner_reuses_the_eval_qa_grader():
    # importing the runner wires grade() from run_eval_qa; a right answer from
    # the right source passes, a refusal does not — same grader as single-turn
    from run_eval_followup import grade

    item = {"type": "table", "expected_answer_contains": ["52 000"],
            "expected_doc": "Avenant du 11 juillet 2023.pdf"}
    cited = [{"filename": "Avenant du 11 juillet 2023.pdf"}]
    ok, _ = grade(item, "Le salaire minimum est de 52 000 € [1].", cited, None)
    assert ok
    bad, _ = grade(item, "Cette information n'est pas dans les documents.", cited, None)
    assert not bad
