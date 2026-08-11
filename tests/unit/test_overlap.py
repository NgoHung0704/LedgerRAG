import uuid

from tablerag.query.overlap import (
    group_overlapping,
    header_signature,
    jaccard,
    subject_signature,
    _fold,
    _WORD,
)
from tablerag.query.pipeline import SourceBlock

SIBLING_A = "<table><tr><th>Garantie</th><th>Montant 2024</th></tr>" \
            "<tr><td>Optique</td><td>100 %</td></tr></table>"
SIBLING_B = "<table><tr><th>Garantie</th><th>Montant 2025</th></tr>" \
            "<tr><td>Optique</td><td>150 %</td></tr></table>"
OTHER = "<table><tr><th>Échelon</th><th>Salaire</th></tr>" \
        "<tr><td>3</td><td>34 900</td></tr></table>"


def _table(html: str, filename: str) -> SourceBlock:
    return SourceBlock(
        kind="table", doc_id=uuid.uuid4(), filename=filename, page=3,
        element_id=uuid.uuid4(), content=html, snippet="", score=0.5,
        crop_image_path="c.png")


def _text(content: str) -> SourceBlock:
    return SourceBlock(
        kind="text", doc_id=uuid.uuid4(), filename="notice.pdf", page=3,
        element_id=uuid.uuid4(), chunk_id=uuid.uuid4(), content=content,
        snippet="", score=0.5, crop_image_path="c.png")


def test_same_headers_different_numbers_share_a_signature():
    assert header_signature(SIBLING_A) == header_signature(SIBLING_B)


def test_different_headers_do_not():
    assert header_signature(SIBLING_A) != header_signature(OTHER)


def test_a_table_with_no_header_row_has_no_signature():
    assert header_signature("<table><tr><td>7</td></tr></table>") is None


BOILERPLATE = ("Le présent document est remis à chaque salarié de l entreprise "
               "conformément aux dispositions légales en vigueur et il est tenu "
               "à la disposition de chaque salarié qui en fait la demande. ")
PREVOYANCE = BOILERPLATE + "Il concerne le régime de prévoyance obligatoire."
KILOMETRIQUE = BOILERPLATE + "Il concerne le barème des indemnités kilométriques."


def _every_word(text: str) -> frozenset[str]:
    """Tokenised the same way, but with nothing filtered out."""
    return frozenset(_fold(word) for word in _WORD.findall(text))


def test_stopword_removal_is_the_only_thing_separating_these_two_chunks():
    # counted word for word they look like the same passage: they share the
    # entire administrative preamble a French notice repeats on every page
    assert jaccard(_every_word(PREVOYANCE), _every_word(KILOMETRIQUE)) > 0.5
    # judged on the rare terms alone they have nothing in common at all
    assert jaccard(subject_signature(PREVOYANCE),
                   subject_signature(KILOMETRIQUE)) < 0.2


def test_identical_text_still_overlaps_completely():
    assert jaccard(subject_signature(PREVOYANCE),
                   subject_signature(PREVOYANCE)) == 1.0


def test_groups_two_sibling_tables_and_leaves_the_third_alone():
    blocks = [_table(SIBLING_A, "notice-2024.pdf"),
              _table(OTHER, "grille.pdf"),
              _table(SIBLING_B, "notice-2025.pdf")]
    assert group_overlapping(blocks) == [[0, 2]]


def test_no_groups_when_nothing_overlaps():
    assert group_overlapping([_table(OTHER, "grille.pdf")]) == []


def test_a_table_and_a_prose_chunk_never_land_in_the_same_group():
    # identical vocabulary on purpose: only the kind check can separate these,
    # so deleting it makes this test fail rather than leaving CI green
    words = "garantie optique niveau remboursement plafond monture verres"
    blocks = [_table(SIBLING_A, "notice.pdf"), _text(words), _text(words)]
    groups = group_overlapping(blocks)
    assert groups == [[1, 2]]


def test_grouping_is_pairwise_and_does_not_chain():
    shared = "prevoyance obligatoire cotisation salarie cadre"
    a = _text(shared + " optique monture verres")
    b = _text(shared + " optique monture dentaire")
    c = _text(shared + " dentaire prothese couronne")
    groups = group_overlapping([a, b, c])
    assert all(len(g) == 2 for g in groups)


def test_a_capitalised_accented_word_matches_its_lowercase_form():
    assert subject_signature("École maternelle") == \
           subject_signature("école maternelle")
