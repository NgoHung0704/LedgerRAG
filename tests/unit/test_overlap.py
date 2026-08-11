import uuid

from tablerag.query.overlap import (
    group_overlapping,
    header_signature,
    jaccard,
    subject_signature,
)
from tablerag.query.pipeline import SourceBlock

SIBLING_A = "<table><tr><th>Garantie</th><th>Niveau 1</th></tr>" \
            "<tr><td>Optique</td><td>100 %</td></tr></table>"
SIBLING_B = "<table><tr><th>Garantie</th><th>Niveau 1</th></tr>" \
            "<tr><td>Optique</td><td>150 %</td></tr></table>"
OTHER = "<table><tr><th>Échelon</th><th>Salaire</th></tr>" \
        "<tr><td>3</td><td>34 900</td></tr></table>"


def _table(html: str, filename: str) -> SourceBlock:
    return SourceBlock(
        kind="table", doc_id=uuid.uuid4(), filename=filename, page=3,
        element_id=uuid.uuid4(), content=html, snippet="", score=0.5,
        crop_image_path="c.png")


def test_same_headers_different_numbers_share_a_signature():
    assert header_signature(SIBLING_A) == header_signature(SIBLING_B)


def test_different_headers_do_not():
    assert header_signature(SIBLING_A) != header_signature(OTHER)


def test_a_table_with_no_header_row_has_no_signature():
    assert header_signature("<table><tr><td>7</td></tr></table>") is None


def test_boilerplate_alone_does_not_make_two_chunks_the_same_subject():
    # the words every French notice repeats; nothing specific is shared
    a = subject_signature("Le présent document est remis à chaque salarié "
                          "de l'entreprise conformément aux dispositions.")
    b = subject_signature("Le présent document est remis à chaque salarié "
                          "de l'entreprise conformément aux dispositions.")
    # identical text does overlap - that is correct - but the rare terms
    # carrying the subject must be what drives it
    assert jaccard(a, b) == 1.0
    c = subject_signature("Le présent document est remis à chaque salarié "
                          "conformément au régime de prévoyance obligatoire.")
    d = subject_signature("Le présent document est remis à chaque salarié "
                          "conformément au barème des indemnités kilométriques.")
    assert jaccard(c, d) < 0.5


def test_groups_two_sibling_tables_and_leaves_the_third_alone():
    blocks = [_table(SIBLING_A, "notice-2024.pdf"),
              _table(OTHER, "grille.pdf"),
              _table(SIBLING_B, "notice-2025.pdf")]
    assert group_overlapping(blocks) == [[0, 2]]


def test_no_groups_when_nothing_overlaps():
    assert group_overlapping([_table(OTHER, "grille.pdf")]) == []
