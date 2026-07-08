"""Document inspector view: all three table representations + provenance."""

from tablerag.storage import repositories as repo


def _seed(s):
    kb = repo.create_kb(s, "HR", "desc")
    doc = repo.create_document(s, kb.id, "rapport.pdf", "kbs/x/docs/y/original.pdf")
    return kb, doc


def test_document_view_exposes_three_table_representations(db_session):
    _, doc = _seed(db_session)
    text_el = repo.add_element(db_session, doc.id, page=1, bbox=[0, 0, 100, 40],
                               type_="text", crop_image_path="t.png", confidence=1.0)
    repo.add_chunks(db_session, text_el.id, [("Article 12: congés payés...", 8)])

    table_el = repo.add_element(db_session, doc.id, page=1, bbox=[0, 50, 100, 90],
                                type_="table", crop_image_path="tab.png")
    repo.add_table_element(db_session, table_el.id, html="<table><tr><td>x</td></tr></table>",
                           summary="CA par pays", n_rows=3, n_cols=2,
                           parse_strategy="vlm")
    repo.add_records(db_session, table_el.id, [
        {"dimensions": {"pays": "Maroc"}, "metrics": {"ca": 5240880},
         "raw_values": {"ca": "5 240 880"}, "text_repr": "Maroc | ca: 5 240 880"},
    ])

    view = repo.get_document_view(db_session, doc.id)
    assert len(view) == 2
    text_view = next(v for v in view if v["type"] == "text")
    assert text_view["chunk_count"] == 1
    assert "congés" in text_view["text_preview"]
    assert text_view["table"] is None

    table_view = next(v for v in view if v["type"] == "table")
    table = table_view["table"]
    assert table["html"].startswith("<table>")           # representation 1
    assert table["records_count"] == 1                    # representation 2
    assert table["records_preview"][0]["raw_values"]["ca"] == "5 240 880"
    assert table["summary"] == "CA par pays"              # representation 3
    assert table["parse_strategy"] == "vlm"


def test_document_view_orders_by_page_then_position(db_session):
    _, doc = _seed(db_session)
    repo.add_element(db_session, doc.id, page=2, bbox=[0, 10, 10, 20],
                     type_="text", crop_image_path="a.png")
    repo.add_element(db_session, doc.id, page=1, bbox=[0, 500, 10, 510],
                     type_="text", crop_image_path="b.png")
    repo.add_element(db_session, doc.id, page=1, bbox=[0, 10, 10, 20],
                     type_="text", crop_image_path="c.png")
    view = repo.get_document_view(db_session, doc.id)
    assert [(v["page"],) for v in view] == [(1,), (1,), (2,)]
    # within page 1, the higher element (smaller y) comes first
    assert view[0]["id"] != view[1]["id"]


def test_document_view_surfaces_honest_failure(db_session):
    _, doc = _seed(db_session)
    element = repo.add_element(
        db_session, doc.id, page=1, bbox=[0, 0, 10, 10], type_="table",
        crop_image_path="bad.png", needs_review=True,
        meta={"parse_error": "contract violation after retry: missing json"})
    repo.add_table_element(db_session, element.id, html="<table></table>",
                           summary=None, n_rows=None, n_cols=None,
                           parse_strategy="vlm")
    [view] = repo.get_document_view(db_session, doc.id)
    assert view["needs_review"] is True
    assert "contract violation" in view["parse_error"]
    assert view["table"]["records_count"] == 0
