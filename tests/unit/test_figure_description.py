"""A figure has no text layer. Stored for provenance it is invisible to
search, so the parser VLM describes it and the description is indexed.

The whole risk of the feature is one line: a DESCRIPTION of a picture is not
text the document states. These tests hold that line — at ingest (a logo must
not become content) and at answer time (a chart reading must not become a
quoted fact).
"""

import re

import pytest

from tablerag.ingestion import ocr
from tablerag.query.pipeline import SourceBlock
from tablerag.query.steps.generate import (
    FIGURE_RULE,
    SYSTEM_PROMPT,
    _render_source,
    build_system_prompt,
)


# --- the INFORMATIVE flag decides whether a picture enters the index --------

@pytest.mark.parametrize("reply,text,informative", [
    ("Bar chart titled « Effectifs par site ».\nINFORMATIVE: yes",
     "Bar chart titled « Effectifs par site ».", True),
    ("Company logo: the word CETIAT in blue.\nINFORMATIVE: no",
     "Company logo: the word CETIAT in blue.", False),
    # case and trailing whitespace are the model's business, not ours
    ("Diagram of the process.\ninformative:  YES  \n",
     "Diagram of the process.", True),
])
@pytest.mark.asyncio
async def test_describe_figure_splits_the_flag_off_the_description(
        monkeypatch, reply, text, informative):
    async def fake(image, prompt):
        return reply

    monkeypatch.setattr(ocr, "_transcribe", fake)
    got_text, got_flag = await ocr.describe_figure(b"png")
    assert (got_text, got_flag) == (text, informative)


@pytest.mark.asyncio
async def test_a_missing_flag_keeps_the_description(monkeypatch):
    """The model dropping the last line must not silently drop the figure:
    treat it as informative and let the reviewer disagree."""
    async def fake(image, prompt):
        return "Un graphique en barres."

    monkeypatch.setattr(ocr, "_transcribe", fake)
    assert await ocr.describe_figure(b"png") == ("Un graphique en barres.", True)


@pytest.mark.asyncio
async def test_the_printed_caption_is_passed_as_evidence(monkeypatch):
    seen = {}

    async def fake(image, prompt):
        seen["prompt"] = prompt
        return "x\nINFORMATIVE: yes"

    monkeypatch.setattr(ocr, "_transcribe", fake)
    await ocr.describe_figure(b"png", "Figure 3 — répartition des effectifs")
    assert "Figure 3 — répartition des effectifs" in seen["prompt"]


def test_the_prompt_forbids_reading_an_unlabelled_value():
    """The one invention a chart invites: putting a number on a bar that has
    none. If this rule ever goes, the feature stops being safe."""
    assert re.search(r"NEVER read a value that is not printed",
                     ocr._FIGURE_PROMPT)


# --- a description must announce itself in the context ---------------------

def _block(**kw) -> SourceBlock:
    base = dict(kind="text", doc_id=None, filename="Rapport.pdf", page=4,
                element_id=None, content="Bar chart of headcount by site.",
                snippet="", score=1.0)
    return SourceBlock(**{**base, **kw})


def test_a_figure_source_is_labelled_as_a_reading_not_as_text():
    rendered = _render_source(2, _block(from_figure=True))
    assert "FIGURE DESCRIPTION" in rendered
    assert "not text" in rendered


def test_an_ordinary_text_source_is_unchanged():
    assert _render_source(2, _block()).startswith("[2] (Rapport.pdf, page 4)")


def test_a_table_source_is_still_a_table():
    assert ", table)" in _render_source(1, _block(kind="table"))


# --- and the rule must not exist when no figure was retrieved --------------

def test_a_corpus_without_figures_gets_the_measured_prompt_byte_for_byte():
    """The answering prompt IS the measured configuration. A KB of text and
    tables must not have its answers moved by a feature it never uses."""
    assert build_system_prompt() == SYSTEM_PROMPT


def test_the_figure_rule_appears_only_when_a_figure_is_a_source():
    with_figures = build_system_prompt(has_figures=True)
    assert with_figures == SYSTEM_PROMPT + FIGURE_RULE
    assert "FIGURE DESCRIPTION" in with_figures


def test_the_figure_rule_layers_under_operator_instructions():
    """Operator guidance is appended last and stays subordinate to the safety
    core — the figure rule must land above it, not after it."""
    prompt = build_system_prompt("Cite les articles.", has_figures=True)
    assert prompt.index("FIGURE DESCRIPTION") < prompt.index("Cite les articles.")


# --- at ingest: what reaches the index ------------------------------------

class _FakeStore:
    def __init__(self):
        self.objects = {}

    def put(self, key, data, content_type="application/octet-stream"):
        self.objects[key] = data


def _ingest_one_figure(db_session, monkeypatch, reply, *, enabled=True, cap=30,
                       describe=None):
    """Run _ingest_page over a page holding a single figure region."""
    import uuid as _uuid

    from tablerag.core.config import get_settings
    from tablerag.ingestion import tasks
    from tablerag.ingestion.layout import PageLayout, Region
    from tablerag.storage import repositories as repo
    from tablerag.storage.orm import Chunk

    async def fake_describe(image, caption=None, groups=None, locale=None,
                            context=None, palette=None):
        return reply

    monkeypatch.setattr(tasks, "describe_figure", describe or fake_describe)
    monkeypatch.setattr(tasks, "crop_region_png", lambda *a, **k: b"crop")

    settings = get_settings()
    monkeypatch.setattr(settings, "figure_describe_enabled", enabled)
    monkeypatch.setattr(settings, "figure_describe_max_per_doc", cap)

    kb = repo.create_kb(db_session, "KB")
    doc = repo.create_document(db_session, kb.id, "r.pdf", "k")
    layout = PageLayout(page=1, width=595, height=842, image_png=b"page",
                        is_scan=False,
                        regions=[Region(type="figure", bbox=(0, 0, 100, 100),
                                        caption="Figure 1")])
    figures: list[_uuid.UUID] = []
    tasks._ingest_page(db_session, _FakeStore(), settings, kb.id, doc.id,
                       layout, None, [], [], [], figures)
    db_session.flush()

    element = repo.get_document_view(db_session, doc.id)[0]
    chunks = db_session.query(Chunk).count()
    return element, chunks, figures


def test_an_informative_figure_becomes_searchable(db_session, monkeypatch):
    element, chunks, figures = _ingest_one_figure(
        db_session, monkeypatch,
        ("Graphique en barres : effectifs par site, axe Y « Nombre de "
         "salariés ».", True))
    assert chunks == 1                       # it is in the index
    assert len(figures) == 1                 # and counted against the budget
    assert element["type"] == "figure"       # still a figure, not text
    assert "effectifs par site" in element["description"]
    assert element["decorative"] is False


def test_a_logo_is_described_but_never_indexed(db_session, monkeypatch):
    """The point of the INFORMATIVE flag: a letterhead on every page would
    otherwise put its description into retrieval once per page."""
    element, chunks, figures = _ingest_one_figure(
        db_session, monkeypatch, ("Logo CETIAT en bleu.", False))
    assert chunks == 0
    assert figures == []
    assert element["decorative"] is True
    assert element["description"] == "Logo CETIAT en bleu."


def test_the_figure_still_exists_when_the_model_fails(db_session, monkeypatch):
    """Honest degradation: a VLM outage costs the description, never the
    element or the document."""
    async def boom(image, caption=None):
        raise RuntimeError("parser unreachable")

    element, chunks, _ = _ingest_one_figure(
        db_session, monkeypatch, None, describe=boom)
    assert element["type"] == "figure"
    assert element["description"] is None
    assert element["caption"] == "Figure 1"   # the document's own words survive
    assert chunks == 0


def test_the_switch_and_the_budget_both_stop_the_vlm(db_session, monkeypatch):
    for kwargs in ({"enabled": False}, {"cap": 0}):
        element, chunks, figures = _ingest_one_figure(
            db_session, monkeypatch, ("should not be called", True), **kwargs)
        assert element["description"] is None, kwargs
        assert (chunks, figures) == (0, []), kwargs


# --- the heading anchor must be a heading ----------------------------------

def test_the_row_above_a_stacked_table_is_not_its_heading():
    """Summaries are what routing matches, so a contaminated one sends the
    question to the wrong table. Measured on a health-insurance notice: the
    optique table was summarised as "Tableau sur le scanner, pose d'implant,
    pilier implantaire" — the last row of the DENTAL table above it."""
    from tablerag.ingestion.layout import nearest_heading

    dental = (42, 395, 553, 568)
    blocks = [(42, 540, 553, 560,
               "Scanner, pose de l'implant, pilier implantaire - par an", 0, 0)]
    optique = (42, 600, 553, 791)
    assert nearest_heading(blocks, optique) is not None      # without the test
    assert nearest_heading(blocks, optique, [dental]) is None


def test_a_real_heading_still_wins():
    from tablerag.ingestion.layout import nearest_heading

    blocks = [(105, 60, 300, 70, "DEFINITIONS DES VERRES :", 0, 0)]
    figure = (105, 75, 489, 338)
    assert nearest_heading(blocks, figure, []) == "DEFINITIONS DES VERRES :"
    # and a region elsewhere on the page does not veto it
    assert nearest_heading(blocks, figure, [(42, 400, 553, 600)]) == \
        "DEFINITIONS DES VERRES :"
