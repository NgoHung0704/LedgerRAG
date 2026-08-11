import uuid

from tablerag.query.neighbours import NeighbourCandidate, choose_neighbours

DOC = uuid.uuid4()
LOWER_DOC = uuid.UUID(int=1)
OWN_DOC = uuid.UUID(int=2)
HIGHER_DOC = uuid.UUID(int=3)


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


def _in(doc: uuid.UUID, page: int, y: float, type_: str = "text") -> NeighbourCandidate:
    return NeighbourCandidate(element_id=uuid.uuid4(), doc_id=doc, page=page,
                              y=y, x=0.0, type=type_)


def test_reading_order_crosses_pages_but_never_documents():
    # fixed ids, and a foreign element on EACH side of the winner: with random
    # uuids and one foreign element this caught the missing document check only
    # about half the time, depending on which way the two ids happened to sort
    before = _in(LOWER_DOC, 1, 100)
    winner = _in(OWN_DOC, 1, 100)
    after = _in(HIGHER_DOC, 1, 100)
    assert choose_neighbours([before, winner, after], [winner.element_id]) == []


def test_vertical_order_runs_down_the_page_not_up():
    # the winner is the LOWER of the two on page 1. Read down the page it has a
    # neighbour on each side; read upwards it becomes the first element in the
    # document and silently loses the page-2 one. A set-equality test with the
    # winner in the middle cannot tell those apart.
    higher_on_page = _c(1, 100)
    winner = _c(1, 300)
    next_page = _c(2, 200)
    picked = set(choose_neighbours([winner, higher_on_page, next_page],
                                   [winner.element_id]))
    assert picked == {higher_on_page.element_id, next_page.element_id}


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *_args):
        return _FakeQuery(self._rows)


class _Row:
    def __init__(self, bbox):
        self.id = uuid.uuid4()
        self.doc_id = DOC
        self.page = 4
        self.bbox = bbox
        self.type = "text"


def test_a_candidate_reads_y_from_bbox_1_and_x_from_bbox_0():
    # bbox is [x0, y0, x1, y1]. Swapping these two indices reverses reading
    # order for every document in the corpus and no other test would notice.
    from tablerag.storage.repositories import get_page_elements

    [candidate] = get_page_elements(_FakeSession([_Row([11.0, 22.0, 33.0, 44.0])]),
                                    [DOC])
    assert (candidate.x, candidate.y) == (11.0, 22.0)


def test_no_documents_means_no_query_at_all():
    from tablerag.storage.repositories import get_page_elements

    assert get_page_elements(_FakeSession([_Row([1.0, 2.0, 3.0, 4.0])]), []) == []
