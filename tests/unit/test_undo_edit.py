"""Taking back an edit.

Reprocessing already undoes anything, but it re-runs the whole document and
throws away every other correction made to it — far too blunt when what you
want back is the last save of one element. So each edit records what the
element held before it, and undo pops that stack.

The edit that matters most here is "this is not a table": it is the only one
that destroys a representation outright, and before this there was no way back
short of reprocessing the file.
"""

import uuid

import pytest

from tablerag import indexing
from tablerag.storage import repositories as repo
from tablerag.storage.orm import Chunk, Element, Record, TableElement


@pytest.fixture
def table(db_session, monkeypatch):
    """A parsed table element, wired so indexing works on the test session."""
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _NullContext(db_session))
    kb = repo.create_kb(db_session, "KB")
    doc = repo.create_document(db_session, kb.id, "f.pdf", "k")
    element = repo.add_element(db_session, doc.id, page=1, bbox=[0, 0, 1, 1],
                               type_="table", crop_image_path="c.png")
    repo.add_table_element(db_session, element.id,
                           "<table><tr><td>Cadres</td><td>120</td></tr></table>",
                           "effectifs par catégorie", 1, 2, "vlm")
    repo.add_records(db_session, element.id, [
        {"dimensions": {"catégorie": "Cadres"}, "metrics": {"effectif": 120},
         "raw_values": {"effectif": "120"}, "text_repr": "Cadres 120"}])
    db_session.flush()
    return element


class _NullContext:
    """Stands in for session_scope on the test's single session.

    Expiring on exit matters: in production each call opens its own scope and
    loads the element fresh, so relationships are never stale. Reusing one
    session without this left `element.chunks` cached and _rechunk deleted
    rows that were no longer the ones there — a test artefact that looked
    exactly like a product bug."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        self.session.flush()
        self.session.expire_all()
        return False


def test_convert_to_table_is_reversible(db_session, table):
    """The one edit that drops a whole representation. Before this, the only
    way back was reprocessing the document."""
    assert indexing.convert_table_to_text(table.id) is True
    db_session.flush()
    assert db_session.get(Element, table.id).type == "text"
    assert db_session.get(TableElement, table.id) is None
    assert db_session.query(Record).count() == 0

    assert indexing.undo_element_edit(table.id) == "convert-to-text"
    db_session.flush()

    restored = db_session.get(Element, table.id)
    assert restored.type == "table"
    grid = db_session.get(TableElement, table.id)
    assert grid is not None
    assert "Cadres" in grid.html and grid.summary == "effectifs par catégorie"
    assert db_session.query(Record).count() == 1


def test_an_edit_can_be_taken_back(db_session, table):
    indexing.apply_element_edit(table.id, html="<table><tr><td>wrong</td></tr></table>",
                                summary="wrong summary")
    db_session.flush()
    assert "wrong" in db_session.get(TableElement, table.id).html

    assert indexing.undo_element_edit(table.id) == "edit"
    db_session.flush()
    grid = db_session.get(TableElement, table.id)
    assert "Cadres" in grid.html
    assert grid.summary == "effectifs par catégorie"


def test_undo_walks_back_through_several_edits(db_session, table):
    """Plain stack semantics, no toggle: pressing it again goes further back,
    which is the more useful of the two behaviours."""
    for n in ("first", "second", "third"):
        indexing.apply_element_edit(table.id, summary=n)
        db_session.flush()

    seen = []
    for _ in range(3):
        indexing.undo_element_edit(table.id)
        db_session.flush()
        seen.append(db_session.get(TableElement, table.id).summary)
    assert seen == ["second", "first", "effectifs par catégorie"]


def test_undo_on_an_untouched_element_does_nothing(db_session, table):
    assert indexing.undo_element_edit(table.id) is None


def test_undo_on_a_missing_element_does_nothing(db_session, table):
    assert indexing.undo_element_edit(uuid.uuid4()) is None


def test_history_is_trimmed(db_session, table):
    """A stack for taking back a mistake, not an archive of the document's
    life — otherwise a heavily reviewed table carries every draft forever."""
    for n in range(repo.MAX_REVISIONS + 5):
        indexing.apply_element_edit(table.id, summary=f"v{n}")
        db_session.flush()
    assert repo.revision_count(db_session, table.id) == repo.MAX_REVISIONS


def test_text_content_comes_back_too(db_session, monkeypatch):
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _NullContext(db_session))
    kb = repo.create_kb(db_session, "KB")
    doc = repo.create_document(db_session, kb.id, "f.pdf", "k")
    element = repo.add_element(db_session, doc.id, page=1, bbox=[0, 0, 1, 1],
                               type_="text", crop_image_path="t.png")
    repo.add_chunks(db_session, element.id, [("the original wording", 4)])
    db_session.flush()

    indexing.apply_element_edit(element.id, text="a replacement")
    db_session.flush()
    assert "replacement" in db_session.query(Chunk).one().text

    assert indexing.undo_element_edit(element.id) == "edit"
    db_session.flush()
    assert db_session.query(Chunk).one().text == "the original wording"


def test_the_crop_image_is_never_versioned(db_session, table):
    """It does not change, and it is the authority a reviewer reads the parse
    against (principle #3) — versioning it would suggest otherwise."""
    before = db_session.get(Element, table.id).crop_image_path
    indexing.apply_element_edit(table.id, summary="x")
    indexing.undo_element_edit(table.id)
    db_session.flush()
    assert db_session.get(Element, table.id).crop_image_path == before


# --- splitting a region detection drew around two tables ------------------

def test_the_seam_answer_is_read_strictly():
    """Row 1 starts the FIRST table, so it is not a seam, and a row past the
    end would cut off nothing. A model that answers with either must not be
    allowed to produce an empty or duplicated part."""
    from tablerag.models.table_parsing import parse_split_rows

    assert parse_split_rows("SPLIT BEFORE ROWS: 7", 12) == [7]
    assert parse_split_rows("SPLIT BEFORE ROWS: 4, 9", 12) == [4, 9]
    assert parse_split_rows("SPLIT BEFORE ROWS: none", 12) == []
    assert parse_split_rows("SPLIT BEFORE ROWS: 1", 12) == []      # not a seam
    assert parse_split_rows("SPLIT BEFORE ROWS: 40", 12) == []     # past the end
    assert parse_split_rows("SPLIT BEFORE ROWS: 7, 7", 12) == [7]
    assert parse_split_rows("I think it is one table.", 12) == []


def test_a_region_is_cut_at_the_row_the_model_named():
    """Each part gets a real bbox, so it can be re-rendered and cropped on its
    own — a split table must be indistinguishable from two that were detected
    separately."""
    from tablerag.indexing import split_bboxes

    rows = [100.0, 120.0, 140.0, 160.0, 180.0]
    parts = split_bboxes([50.0, 100.0, 300.0, 200.0], rows, [4])
    assert parts == [[50.0, 100.0, 300.0, 160.0],
                     [50.0, 160.0, 300.0, 200.0]]


def test_a_seam_outside_the_region_is_ignored():
    from tablerag.indexing import split_bboxes

    rows = [100.0, 120.0, 900.0]
    assert split_bboxes([50.0, 100.0, 300.0, 200.0], rows, [3]) == [
        [50.0, 100.0, 300.0, 200.0]]


def test_undoing_a_split_takes_the_parts_with_it(db_session, table,
                                                 monkeypatch):
    """Otherwise undo restores the first table to its full range while its
    siblings still stand — the same rows indexed twice, which is worse than
    the merge it was undoing."""
    from tablerag import indexing

    monkeypatch.setattr(indexing, "_drop_crops", lambda *a, **k: None)
    doc_id = db_session.get(Element, table.id).doc_id
    repo.snapshot_element(db_session, table.id, "split")
    part2 = repo.add_element(db_session, doc_id, page=1, bbox=[0, 0, 1, 1],
                             type_="table", crop_image_path="p2.png",
                             meta={"split_from": str(table.id)})
    db_session.flush()
    assert repo.split_children(db_session, table.id) == [part2.id]

    assert indexing.undo_element_edit(table.id) == "split"
    db_session.flush()
    assert db_session.get(Element, part2.id) is None
    assert db_session.get(Element, table.id) is not None


def test_every_way_a_split_can_end_says_which_one_it_was(monkeypatch):
    """Five situations reach the same refusal, and one message claiming the
    model decided was wrong about four of them. The reviewer pressed a button,
    saw nothing, and had no way to tell a refusal from a success."""
    import asyncio

    from tablerag import indexing

    cases = {
        "no source": (None, "no longer available"),
        "cross page": ({"spans_pages": True}, "merged across pages"),
        "no grid": ({"spans_pages": False, "pdf": b"", "page": 1,
                     "bbox": [0, 0, 1, 1]}, "no row grid"),
    }
    for name, (info, expected) in cases.items():
        monkeypatch.setattr(indexing, "_table_region_inputs", lambda _e, i=info: i)
        monkeypatch.setattr(indexing, "_region_rows", lambda *a: (None, []))
        parts, reason = asyncio.run(indexing.split_table(uuid.uuid4()))
        assert parts is None, name
        assert expected in reason, f"{name}: {reason}"
