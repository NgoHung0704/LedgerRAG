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
