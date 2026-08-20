"""Reading a retrieved table's own rows, to answer a filter question.

`rows_by_named_value` needs the dimensions of every row of a table that is
already in context. Retrieval never asked for them — it only ever knew the rows
its own ranking surfaced — so there was no way to fetch them.

Keyed BY ELEMENT, not returned as one flat list: two tables can both be in
context, and a row of the grading grid must not be offered as a row of the pay
scale. That confusion is the whole family of bugs this area keeps producing.
"""


from tablerag.storage import repositories as repo


def _table(db_session, doc_id, rows):
    element = repo.add_element(db_session, doc_id, 1, [0, 0, 1, 1],
                               "table", "crop.png")
    repo.add_table_element(db_session, element.id, "<table></table>", None,
                           len(rows), 2, "words")
    repo.add_records(db_session, element.id,
                     [{"dimensions": d, "metrics": {}, "raw_values": {},
                       "text_repr": " | ".join(f"{k}: {v}" for k, v in d.items())}
                      for d in rows])
    return element.id


def _doc(db_session):
    kb = repo.create_kb(db_session, "KB", "", {})
    return repo.create_document(db_session, kb.id, "cotation.pdf", "k").id


def test_every_row_of_the_table_comes_back_with_its_dimensions(db_session):
    doc_id = _doc(db_session)
    element_id = _table(db_session, doc_id, [
        {"emploi": "Chargé(e) de Maintenance", "classe": "10"},
        {"emploi": "Gestionnaire Parc Mesure", "classe": "10"},
        {"emploi": "Comptable", "classe": "7"},
    ])
    got = repo.get_record_dimensions(db_session, [element_id])
    assert set(got) == {element_id}
    assert [d for _, d in got[element_id]] == [
        {"emploi": "Chargé(e) de Maintenance", "classe": "10"},
        {"emploi": "Gestionnaire Parc Mesure", "classe": "10"},
        {"emploi": "Comptable", "classe": "7"},
    ]


def test_rows_stay_filed_under_the_table_they_belong_to(db_session):
    # the look-alike failure in miniature: two grids in context at once, and a
    # row of one offered as a row of the other
    doc_id = _doc(db_session)
    grading = _table(db_session, doc_id, [{"emploi": "X", "classe": "10"}])
    scale = _table(db_session, doc_id, [{"classe": "10", "smh": "34 900"}])
    got = repo.get_record_dimensions(db_session, [grading, scale])
    assert [d for _, d in got[grading]] == [{"emploi": "X", "classe": "10"}]
    assert [d for _, d in got[scale]] == [{"classe": "10", "smh": "34 900"}]


def test_a_table_with_no_records_is_absent_rather_than_empty(db_session):
    doc_id = _doc(db_session)
    element = repo.add_element(db_session, doc_id, 1, [0, 0, 1, 1],
                               "table", "crop.png")
    repo.add_table_element(db_session, element.id, "<table></table>", None,
                           0, 0, "words")
    assert repo.get_record_dimensions(db_session, [element.id]) == {}


def test_asking_for_nothing_touches_no_table(db_session):
    assert repo.get_record_dimensions(db_session, []) == {}


def test_the_ids_are_the_record_ids_the_context_step_will_fetch(db_session):
    doc_id = _doc(db_session)
    element_id = _table(db_session, doc_id, [{"emploi": "X", "classe": "10"}])
    (record_id, _), = repo.get_record_dimensions(db_session, [element_id])[element_id]
    assert repo.get_record_texts(db_session, [record_id]) == {
        record_id: "emploi: X | classe: 10"}
