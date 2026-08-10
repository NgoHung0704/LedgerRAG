"""Correcting what the model saw in a picture.

A figure's stored description is the only searchable thing it has, so a wrong
one is a fact the corpus now asserts. It could be deleted or reprocessed, but
not fixed — the editor refused figures outright.

What is INDEXED is not the description alone: it is the heading above the
figure and its measured palette prefixed to it. A reviewer correcting the
description must not have to retype those, nor be able to lose them.
"""

from tablerag import indexing
from tablerag.storage import repositories as repo
from tablerag.storage.orm import Chunk, Element

META = {
    "context": "DEFINITIONS DES VERRES :",
    "palette": [{"name": "turquoise", "hex": "#6d9cb0", "share": 0.32},
                {"name": "rouge", "hex": "#ef7d63", "share": 0.24}],
    "description": "Diagramme de classification.",
}


def test_the_indexed_text_is_the_anchors_then_the_description():
    assert indexing.figure_index_text(META) == (
        "DEFINITIONS DES VERRES :\n\n"
        "turquoise (#6d9cb0, 32%), rouge (#ef7d63, 24%)\n\n"
        "Diagramme de classification.")


def test_a_figure_with_no_anchors_is_just_its_description():
    assert indexing.figure_index_text(
        {"description": "Logo de l'entreprise."}) == "Logo de l'entreprise."


def test_the_palette_is_formatted_by_the_one_formatter():
    """Ingestion writes the palette line from measured tuples, this rebuilds it
    from the dicts they are stored as. Two formatters would drift, and the
    indexed text would stop matching what ingestion produced."""
    from tablerag.ingestion.palette import describe_palette

    assert (describe_palette(META["palette"])
            == describe_palette([("turquoise", "#6d9cb0", 0.32),
                                 ("rouge", "#ef7d63", 0.24)]))


def _figure(db_session, monkeypatch):
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _Null(db_session))
    kb = repo.create_kb(db_session, "KB")
    doc = repo.create_document(db_session, kb.id, "f.pdf", "k")
    element = repo.add_element(db_session, doc.id, page=9, bbox=[0, 0, 1, 1],
                               type_="figure", crop_image_path="c.png",
                               meta=dict(META))
    repo.add_chunks(db_session, element.id,
                    [(indexing.figure_index_text(META), 20)])
    db_session.flush()
    return element


class _Null:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        self.session.flush()
        self.session.expire_all()
        return False


def test_editing_a_figure_rewrites_its_description_and_its_index(
        db_session, monkeypatch):
    element = _figure(db_session, monkeypatch)
    assert indexing.apply_element_edit(
        element.id, text="Le turquoise marque les verres complexes.")
    db_session.flush()

    stored = db_session.get(Element, element.id)
    assert stored.meta["description"] == "Le turquoise marque les verres complexes."
    chunk = db_session.query(Chunk).one().text
    # the correction is indexed, and the anchors survived it
    assert "Le turquoise marque les verres complexes." in chunk
    assert chunk.startswith("DEFINITIONS DES VERRES :")
    assert "turquoise (#6d9cb0, 32%)" in chunk


def test_a_correction_can_be_taken_back(db_session, monkeypatch):
    element = _figure(db_session, monkeypatch)
    indexing.apply_element_edit(element.id, text="une lecture erronée")
    db_session.flush()
    assert indexing.undo_element_edit(element.id) == "edit"
    db_session.flush()
    assert "Diagramme de classification." in db_session.query(Chunk).one().text
