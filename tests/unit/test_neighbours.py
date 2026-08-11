import uuid

from tablerag.query.neighbours import NeighbourCandidate, choose_neighbours

DOC = uuid.uuid4()


def _c(page: int, y: float, type_: str = "text") -> NeighbourCandidate:
    return NeighbourCandidate(element_id=uuid.uuid4(), doc_id=DOC, page=page,
                              y=y, x=0.0, type=type_)


def test_a_text_winner_takes_the_element_before_and_after_it():
    a, b, c = _c(1, 100), _c(1, 200), _c(1, 300)
    picked = choose_neighbours([a, b, c], [b.element_id])
    assert set(picked) == {a.element_id, c.element_id}


def test_a_table_pulls_no_neighbours_of_its_own():
    a, table, c = _c(1, 100), _c(1, 200, "table"), _c(1, 300)
    assert choose_neighbours([a, table, c], [table.element_id]) == []


def test_every_table_and_figure_on_the_winner_s_page_comes_along():
    text = _c(2, 100)
    table = _c(2, 400, "table")
    figure = _c(2, 600, "figure")
    elsewhere = _c(3, 100, "table")
    picked = choose_neighbours([text, table, figure, elsewhere],
                               [text.element_id])
    assert table.element_id in picked and figure.element_id in picked
    assert elsewhere.element_id not in picked


def test_a_winner_is_never_returned_as_its_own_neighbour():
    a, b = _c(1, 100), _c(1, 200)
    picked = choose_neighbours([a, b], [a.element_id, b.element_id])
    assert picked == []


def test_reading_order_crosses_pages_but_never_documents():
    other_doc = NeighbourCandidate(element_id=uuid.uuid4(), doc_id=uuid.uuid4(),
                                   page=1, y=150, x=0.0, type="text")
    a, b = _c(1, 100), _c(1, 200)
    picked = choose_neighbours([a, b, other_doc], [b.element_id])
    assert other_doc.element_id not in picked
