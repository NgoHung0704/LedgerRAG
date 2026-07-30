"""Manual element editing (Postgres side) + document purge helper.

The re-embedding half of indexing.reindex_element needs a live embedder +
Qdrant, so it's exercised by integration/eval, not here. These cover the
deterministic Postgres mutations and their guardrails."""

import uuid

import pytest

from tablerag import indexing
from tablerag.storage import repositories as repo
from tablerag.storage.orm import Chunk, Record


def _seed_text(db_session):
    kb = repo.create_kb(db_session, "HR", "d")
    doc = repo.create_document(db_session, kb.id, "r.pdf", "kbs/x/y/o.pdf")
    el = repo.add_element(db_session, doc.id, page=1, bbox=[0, 0, 1, 1],
                          type_="text", crop_image_path="c.png", confidence=1.0)
    repo.add_chunks(db_session, el.id, [("old text one", 3), ("old two", 2)])
    return doc, el


def _seed_table(db_session):
    kb = repo.create_kb(db_session, "HR", "d")
    doc = repo.create_document(db_session, kb.id, "r.pdf", "kbs/x/y/o.pdf")
    el = repo.add_element(db_session, doc.id, page=1, bbox=[0, 0, 1, 1],
                          type_="table", crop_image_path="c.png",
                          needs_review=True)
    repo.add_table_element(db_session, el.id, "<table><tr><td>old</td></tr></table>",
                           "old summary", 1, 1, "vlm")
    repo.add_records(db_session, el.id, [
        {"dimensions": {"pays": "Maroc"}, "metrics": {"ca": 100},
         "raw_values": {"ca": "100"}, "text_repr": "Maroc | ca: 100"}])
    return doc, el


def test_edit_text_rechunks(db_session, monkeypatch):
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    _, el = _seed_text(db_session)
    ok = indexing.apply_element_edit(el.id, text="brand new corrected content")
    assert ok is True
    chunks = db_session.query(Chunk).filter(Chunk.element_id == el.id).all()
    assert len(chunks) == 1
    assert "brand new corrected" in chunks[0].text
    assert "old text one" not in chunks[0].text
    from tablerag.storage.orm import Element
    assert db_session.get(Element, el.id).meta["edited"] is True


def test_edit_table_updates_html_summary_records(db_session, monkeypatch):
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    _, el = _seed_table(db_session)
    ok = indexing.apply_element_edit(
        el.id, html="<table><tr><td>fixed</td></tr></table>",
        summary="corrected summary",
        records=[{"dimensions": {"pays": "France"}, "metrics": {"ca": 7462639},
                  "raw_values": {"ca": "7 462 639"}}])
    assert ok is True
    from tablerag.storage.orm import Element, TableElement
    table = db_session.get(TableElement, el.id)
    assert "fixed" in table.html
    assert table.summary == "corrected summary"
    records = db_session.query(Record).filter(
        Record.table_element_id == el.id).all()
    assert len(records) == 1
    assert records[0].dimensions == {"pays": "France"}
    assert records[0].metrics == {"ca": 7462639}
    assert "France" in records[0].text_repr and "7 462 639" in records[0].text_repr
    # editing clears the review flag
    assert db_session.get(Element, el.id).needs_review is False
    assert db_session.get(Element, el.id).meta["edited"] is True


def test_convert_a_wrongly_detected_table_to_text(db_session, monkeypatch):
    """Detection sometimes fires on prose in columns. Demoting it must keep the
    page's own words, drop the grid and records, and leave provenance intact."""
    from tablerag.storage.orm import Element, TableElement

    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    _, el = _seed_table(db_session)

    assert indexing.convert_table_to_text(el.id) is True

    element = db_session.get(Element, el.id)
    assert element.type == "text"
    assert element.needs_review is False
    assert element.meta["converted_from"] == "table"
    # the crop image is untouched: every element still traces to its origin
    assert element.crop_image_path == "c.png"

    # the table is gone, records with it
    assert db_session.get(TableElement, el.id) is None
    assert db_session.query(Record).filter(
        Record.table_element_id == el.id).count() == 0

    # and the cells' own words are now the indexed text — nothing invented
    chunks = db_session.query(Chunk).filter(Chunk.element_id == el.id).all()
    assert chunks and "old" in chunks[0].text


def test_convert_refuses_anything_that_is_not_a_table(db_session, monkeypatch):
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    _, text_el = _seed_text(db_session)
    assert indexing.convert_table_to_text(text_el.id) is False
    assert indexing.convert_table_to_text(uuid.uuid4()) is False
    # the text element is left exactly as it was
    chunks = db_session.query(Chunk).filter(Chunk.element_id == text_el.id).all()
    assert len(chunks) == 2


def test_convert_an_image_only_table_still_succeeds(db_session, monkeypatch):
    """A table whose parse failed has no HTML: it becomes an empty text element
    the reviewer can fill with 're-read with the VLM' — better than staying a
    table that never had a grid."""
    from tablerag.storage.orm import Element

    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    kb = repo.create_kb(db_session, "HR", "d")
    doc = repo.create_document(db_session, kb.id, "r.pdf", "k")
    el = repo.add_element(db_session, doc.id, page=1, bbox=[0, 0, 1, 1],
                          type_="table", crop_image_path="c.png")
    repo.add_table_element(db_session, el.id, None, None, None, None, "vlm")

    assert indexing.convert_table_to_text(el.id) is True
    assert db_session.get(Element, el.id).type == "text"


def test_recheck_uses_the_stitched_crop_for_a_cross_page_table(monkeypatch):
    """A merged cross-page table's stored crop is the stitched image of its
    fragments. Re-rendering one page would hand the model HALF the table and
    call it a more careful read."""
    import asyncio

    from tablerag.ingestion import table_pipeline

    monkeypatch.setattr(
        indexing, "_table_region_inputs",
        lambda eid: {"spans_pages": True, "crop": b"stitched-png",
                     "locale": "fr", "page": 3, "bbox": [0, 0, 1, 1]})
    monkeypatch.setattr(
        indexing, "_render_region",
        lambda *a, **k: pytest.fail("a spanning table must not be re-rendered"))

    seen: dict = {}

    async def fake_parse(crop, grid, is_complex, locale, read_variant=0,
                         provider=None):
        seen["crop"] = crop
        return table_pipeline.TableResult(html="<table/>", parse_strategy="vlm")

    monkeypatch.setattr(table_pipeline, "parse_table_region", fake_parse)
    out = asyncio.run(indexing.recheck_table(uuid.uuid4()))

    assert seen["crop"] == b"stitched-png"   # the whole table, not one page
    assert out["stitched"] is True
    assert out["dpi"] is None                # nothing was re-rendered


def test_recheck_refuses_a_non_table(db_session, monkeypatch):
    """The guard itself, called directly: the DB lookup runs in a worker thread
    under asyncio, which this test's SQLite session cannot cross."""
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    _, text_el = _seed_text(db_session)
    assert indexing._table_region_inputs(text_el.id) is None
    assert indexing._table_region_inputs(uuid.uuid4()) is None


def test_recheck_gives_up_when_the_source_is_gone(monkeypatch):
    """No PDF (deleted, or never stored) -> no proposal, and no model call."""
    import asyncio

    from tablerag.ingestion import table_pipeline

    monkeypatch.setattr(indexing, "_table_region_inputs", lambda eid: None)
    monkeypatch.setattr(
        table_pipeline, "parse_table_region",
        lambda *a, **k: pytest.fail("must not parse without a source"))
    assert asyncio.run(indexing.recheck_table(uuid.uuid4())) is None


def test_recheck_checks_the_first_read_and_proposes_the_correction(
        db_session, monkeypatch):
    """The second look is a CHECK, not a blind re-read: it is handed the first
    reading to fault against the image, and its correction is what gets
    proposed — with the agreement saying how much it changed."""
    import asyncio

    from tablerag.ingestion import table_pipeline
    from tablerag.models import base as models_base
    from tablerag.models import registry

    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    _, el = _seed_table(db_session)

    first = [{"dimensions": {"classe": "16"}, "metrics": {"smh": 52000},
              "raw_values": {"smh": "52 000"}}]
    parses: list[dict] = []
    renders: list[int] = []

    async def fake_parse(crop, grid, is_complex, locale, read_variant=0,
                         provider=None):
        parses.append({"is_complex": is_complex, "grid": grid})
        return table_pipeline.TableResult(
            html="<table><tr><td>16</td><td>52 000</td></tr></table>",
            parse_strategy="vlm", records=first)

    seen_check: dict = {}

    async def fake_verify(chat, image, ctx, html, records, grid_hint=None):
        seen_check["html"] = html
        seen_check["records"] = records
        seen_check["grid_hint"] = grid_hint
        # it must fault the reading before correcting it
        from tablerag.models.table_parsing import TableVerification

        return TableVerification(
            parse=models_base.TableParse(
                html="<table><tr><td>16</td><td>52 800</td></tr></table>",
                records=[models_base.RecordParse(
                    dimensions={"classe": "16"}, metrics={"smh": 52800},
                    raw_values={"smh": "52 800"})]),
            findings='FINDINGS:\n- row 1, column "smh": image shows "52 800"',
            clean=False)

    def fake_render(pdf, page, bbox, dpi):
        renders.append(dpi)
        return b"png", [["a"]]

    monkeypatch.setattr(indexing, "_table_region_inputs",
                        lambda eid: {"pdf": b"%PDF", "page": 1,
                                     "bbox": [0, 0, 10, 10], "locale": "fr",
                                     "spans_pages": False})
    monkeypatch.setattr(indexing, "_render_region", fake_render)
    monkeypatch.setattr(table_pipeline, "parse_table_region", fake_parse)
    monkeypatch.setattr(registry, "get_double_read_provider", lambda: None)
    monkeypatch.setattr(indexing, "get_provider",
                        lambda role: type("P", (), {"chat": None})())
    monkeypatch.setattr("tablerag.models.table_parsing.run_table_verify", fake_verify)

    out = asyncio.run(indexing.recheck_table(el.id))

    assert out is not None
    # ONE parse (forced down the VLM path), then a check of it
    assert len(parses) == 1 and parses[0]["is_complex"] is True
    assert seen_check["records"] == first        # the check saw the first read
    assert "52 000" in seen_check["html"]
    # the check gets the sharper render
    assert renders == [480, 600]
    assert out["dpi"] == 480 and out["grid_hint"] is True
    # and its correction is what is proposed
    assert out["records"][0]["raw_values"]["smh"] == "52 800"
    assert "52 800" in out["html"]
    assert out["second_read"] is True
    assert out["signals"]["agreement"] < 1.0     # it changed something
    # it had to name the fault before correcting, and the reviewer sees it
    assert "52 800" in out["findings"] and out["clean"] is False
    assert seen_check["grid_hint"] is not None   # text-layer values to compare
    # nothing was written: the stored table is untouched
    from tablerag.storage.orm import TableElement
    assert db_session.get(TableElement, el.id).html == \
        "<table><tr><td>old</td></tr></table>"


def test_recheck_keeps_the_first_read_when_the_check_fails(db_session, monkeypatch):
    """A failed verification must cost nothing."""
    import asyncio

    from tablerag.ingestion import table_pipeline
    from tablerag.models import registry

    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    _, el = _seed_table(db_session)
    first = [{"dimensions": {"classe": "16"}, "metrics": {"smh": 52000},
              "raw_values": {"smh": "52 000"}}]

    async def fake_parse(crop, grid, is_complex, locale, read_variant=0,
                         provider=None):
        return table_pipeline.TableResult(
            html="<table><tr><td>first</td></tr></table>",
            parse_strategy="vlm", records=first)

    async def failing_verify(chat, image, ctx, html, records, grid_hint=None):
        from tablerag.models.table_parsing import TableVerification

        return TableVerification(parse=None)  # contract violated twice

    monkeypatch.setattr(indexing, "_table_region_inputs",
                        lambda eid: {"pdf": b"%PDF", "page": 1,
                                     "bbox": [0, 0, 10, 10], "locale": "fr",
                                     "spans_pages": False})
    monkeypatch.setattr(indexing, "_render_region",
                        lambda *a, **k: (b"png", None))
    monkeypatch.setattr(table_pipeline, "parse_table_region", fake_parse)
    monkeypatch.setattr(registry, "get_double_read_provider", lambda: None)
    monkeypatch.setattr(indexing, "get_provider",
                        lambda role: type("P", (), {"chat": None})())
    monkeypatch.setattr("tablerag.models.table_parsing.run_table_verify",
                        failing_verify)

    out = asyncio.run(indexing.recheck_table(el.id))
    assert "first" in out["html"]                     # the first read stands
    assert out["records"][0]["raw_values"]["smh"] == "52 000"
    assert out["second_read"] is False                # and it says so


def test_derive_rebuilds_records_from_corrected_html(db_session, monkeypatch):
    """Fixing the HTML alone leaves answers quoting the OLD records. Deriving
    reads them back out of the corrected grid, merged cells expanded."""
    import asyncio

    from tablerag.ingestion import table_pipeline

    monkeypatch.setattr(indexing, "_element_locale", lambda eid: (True, "fr"))

    async def fake_summary(html, locale=None):
        return "Barème des salaires par classe"

    monkeypatch.setattr(table_pipeline, "summarize_table", fake_summary)

    # a rowspan: "F" covers both rows, so row 2 has one cell fewer
    html = (
        "<table>"
        "<tr><th>Groupe</th><th>Classe</th><th>SMH</th></tr>"
        "<tr><td rowspan='2'>F</td><td>11</td><td>34 900</td></tr>"
        "<tr><td>12</td><td>36 700</td></tr>"
        "</table>"
    )
    out = asyncio.run(indexing.derive_from_html(uuid.uuid4(), html))

    assert out is not None
    assert out["rows"] == 3 and out["cols"] == 3
    assert out["summary"] == "Barème des salaires par classe"
    assert len(out["records"]) == 2
    # the spanned group is repeated on the row it covers — the whole point
    assert [r["dimensions"]["groupe"] for r in out["records"]] == ["F", "F"]
    # and the French number is read with its locale, raw string preserved
    assert out["records"][0]["raw_values"]["smh"] == "34 900"
    assert out["records"][0]["metrics"]["smh"] == 34900


def test_derive_keeps_the_old_records_when_it_cannot_read_a_grid(monkeypatch):
    """Better to say nothing than to wipe the records with an empty list."""
    import asyncio

    from tablerag.ingestion import table_pipeline

    monkeypatch.setattr(indexing, "_element_locale", lambda eid: (True, None))

    async def fake_summary(html, locale=None):
        return None

    monkeypatch.setattr(table_pipeline, "summarize_table", fake_summary)
    out = asyncio.run(indexing.derive_from_html(uuid.uuid4(), "<p>not a table</p>"))
    assert out is not None
    assert out["records"] == [] and out["rows"] == 0


def test_derive_on_a_missing_element(monkeypatch):
    import asyncio

    monkeypatch.setattr(indexing, "_element_locale", lambda eid: (False, None))
    assert asyncio.run(indexing.derive_from_html(uuid.uuid4(), "<table/>")) is None


def test_edit_missing_element_returns_false(db_session, monkeypatch):
    monkeypatch.setattr(indexing, "session_scope",
                        lambda: _fake_scope(db_session))
    assert indexing.apply_element_edit(uuid.uuid4(), text="x") is False


def test_document_view_reports_edited_flag(db_session):
    from tablerag.storage.orm import Element

    _, el = _seed_table(db_session)
    db_session.get(Element, el.id).meta = {"edited": True}
    db_session.flush()
    view = repo.get_document_view(db_session, el.doc_id)
    assert view[0]["edited"] is True


# -- helper: make indexing.apply_element_edit use the test session ------------

class _fake_scope:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        self.session.flush()
        return False
