"""What is printed on the pages an answer used, offered to be looked at.

A chart's numbers live in its drawing, not in its description, so an answer
about a topic is nearly always written from the prose beside the chart. The
description is a paraphrase competing against the original and it loses — which
is why a figure cannot be reached by ranking alone and has to be offered.

Bounded to the pages the answer CITED. The unbounded version of this was
measured and rejected: 18-53 blocks a query, citations 12 -> 52, traps 3/7 ->
1/7. Nothing here enters the model's context; it is a list to click.
"""

import uuid

from tablerag.storage import repositories as repo
from tablerag.storage.repositories import get_page_visuals


def _doc(s, filename: str):
    kb = repo.create_kb(s, "kb")
    return repo.create_document(s, kb.id, filename, "orig.pdf")


def _element(s, doc, page: int, type_: str, meta: dict | None = None):
    return repo.add_element(s, doc.id, page, [0, 0, 10, 10], type_,
                            f"crops/{uuid.uuid4()}.png", meta=meta or {})


def test_a_figure_on_a_cited_page_is_offered(db_session):
    doc = _doc(db_session, "notice.pdf")
    figure = _element(db_session, doc, 3, "figure",
                      {"context": "Répartition sectorielle"})
    out = get_page_visuals(db_session, [(doc.id, 3)], exclude=set())
    assert [v.element_id for v in out] == [figure.id]
    assert out[0].filename == "notice.pdf" and out[0].page == 3
    assert out[0].context == "Répartition sectorielle"


def test_a_figure_on_a_page_the_answer_never_used_is_not(db_session):
    doc = _doc(db_session, "notice.pdf")
    _element(db_session, doc, 9, "figure")
    assert get_page_visuals(db_session, [(doc.id, 3)], exclude=set()) == []


def test_a_source_the_answer_already_cited_is_not_offered_twice(db_session):
    doc = _doc(db_session, "notice.pdf")
    figure = _element(db_session, doc, 3, "figure")
    assert get_page_visuals(db_session, [(doc.id, 3)],
                            exclude={figure.id}) == []


def test_plain_text_on_the_page_is_not_offered(db_session):
    # the offer is for things a reader must LOOK at. Page prose was already
    # in front of the ranker on its own terms and lost or won there.
    doc = _doc(db_session, "notice.pdf")
    _element(db_session, doc, 3, "text")
    assert get_page_visuals(db_session, [(doc.id, 3)], exclude=set()) == []


def test_figures_come_before_tables(db_session):
    # a table's cells are text and can be reached by ranking; a figure's
    # numbers are in the drawing and cannot. Under a cap, the figure goes first.
    doc = _doc(db_session, "notice.pdf")
    table = _element(db_session, doc, 3, "table")
    figure = _element(db_session, doc, 3, "figure")
    out = get_page_visuals(db_session, [(doc.id, 3)], exclude=set())
    assert [v.element_id for v in out] == [figure.id, table.id]


def test_the_offer_is_capped(db_session):
    # a dense factsheet page carries several tables and charts; three cited
    # pages would put twenty chips under an answer and the list stops being
    # read at all
    doc = _doc(db_session, "notice.pdf")
    for _ in range(10):
        _element(db_session, doc, 3, "figure")
    assert len(get_page_visuals(db_session, [(doc.id, 3)], exclude=set())) == 6


def test_a_page_of_another_document_with_the_same_number_is_not_mixed_in(db_session):
    # pairs are (document, page). Filtering documents and pages separately and
    # forgetting to pair them back up offers page 3 of every cited document.
    a = _doc(db_session, "a.pdf")
    b = _doc(db_session, "b.pdf")
    _element(db_session, a, 3, "figure")
    stray = _element(db_session, b, 3, "figure")
    wanted = _element(db_session, b, 8, "figure")
    out = get_page_visuals(db_session, [(a.id, 3), (b.id, 8)], exclude=set())
    ids = {v.element_id for v in out}
    assert wanted.id in ids and stray.id not in ids
