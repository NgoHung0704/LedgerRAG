import uuid

from tablerag.query.overlap import overlap_note, period_of
from tablerag.query.pipeline import SourceBlock
from tablerag.query.steps.generate import OVERLAP_RULE, build_system_prompt


def _table(filename: str, context: str = "") -> SourceBlock:
    return SourceBlock(
        kind="table", doc_id=uuid.uuid4(), filename=filename, page=3,
        element_id=uuid.uuid4(), content="<table></table>", snippet="",
        score=0.5, crop_image_path="c.png", context=context)


def test_period_is_read_from_a_year_or_a_quarter():
    assert period_of("Notice 2024.pdf", "") == "2024"
    assert period_of("notice.pdf", "Résultats T1") == "T1"
    assert period_of("notice.pdf", "Garanties") is None


def test_the_note_names_each_source_by_number_and_provenance():
    blocks = [_table("notice-2024.pdf", "Garanties optique"),
              _table("notice-2025.pdf", "Garanties optique")]
    note = overlap_note(blocks, [[0, 1]])
    assert "[1]" in note and "[2]" in note
    assert "notice-2024.pdf" in note and "notice-2025.pdf" in note
    assert "Garanties optique" in note


def test_no_groups_means_no_note():
    assert overlap_note([_table("a.pdf")], []) == ""


def test_the_contrast_rule_is_absent_unless_there_is_an_overlap():
    assert OVERLAP_RULE not in build_system_prompt()
    assert OVERLAP_RULE in build_system_prompt(has_overlap=True)


# The rule has TWO branches, and the split is the whole point of it. Before,
# it said "Never merge them into a single statement" unconditionally, so two
# documents printing the same value were still split into two attributed
# sentences — noise the reader has to reconcile by hand.
#
# These assertions read the prompt's TEXT, which is all a unit test can do to a
# prompt: whether the model obeys is measured by the `concordant` and
# `contrast` questions in tests/eval/qa, on the box. What they do guard is a
# revert or a half-edit that drops one branch and leaves the rule lopsided.
#
# Lowercased before matching: the prompt SHOUTS its key terms, and a test that
# broke when emphasis moved from "SAME VALUE" to "same value" would be guarding
# typography rather than the rule.

def test_the_rule_lets_agreeing_sources_be_stated_once():
    rule = build_system_prompt(has_overlap=True).lower()
    assert "never merge" not in rule, \
        "the unconditional prohibition is what this change removed"
    assert "same value" in rule


def test_the_rule_still_forbids_merging_sources_that_differ():
    rule = build_system_prompt(has_overlap=True).lower()
    assert "differs" in rule
    # naming the document is what makes a difference legible to the reader
    assert "which document" in rule


def test_agreement_must_still_carry_every_source():
    # a merged statement cites the whole group; citing one of them would hide
    # that the others were checked at all
    assert "cite all of them" in build_system_prompt(has_overlap=True).lower()
