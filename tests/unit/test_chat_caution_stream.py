import pathlib
import re
import uuid

import pytest

from tablerag.core.schemas import Citation
from tablerag.query.pipeline import QueryContext, caution_event

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _figure_citation() -> Citation:
    return Citation(index=1, kind="text", doc_id=uuid.uuid4(), filename="f.pdf",
                    page=1, element_id=uuid.uuid4(), snippet="", score=0.1,
                    from_figure=True)


def test_a_finished_answer_resting_on_a_figure_produces_a_caution():
    ctx = QueryContext(kb_id=uuid.uuid4(), question="q")
    ctx.answer = "Le graphique montre 27 % [1]."
    ctx.citations = [_figure_citation()]
    ctx.escalation_contact = "service RH"
    event = caution_event(ctx)
    assert event is not None
    assert event.contact == "service RH"
    assert "figure_reading" in event.reasons


def test_an_ordinary_answer_produces_none():
    ctx = QueryContext(kb_id=uuid.uuid4(), question="q")
    ctx.answer = "La valeur est 34 900 [1]."
    ctx.citations = [Citation(index=1, kind="table", doc_id=uuid.uuid4(),
                              filename="f.pdf", page=1,
                              element_id=uuid.uuid4(), snippet="", score=0.9,
                              confidence=1.0)]
    assert caution_event(ctx) is None


def test_a_broken_citation_list_costs_the_warning_not_the_answer():
    # the global rule: a feature must never fail an answer. caution_event is
    # called after generation, so an exception here would throw away an answer
    # the user already watched stream in.
    class _Broken:
        # `index` must MATCH the cited marker, or the object is filtered out
        # before anything touches it and nothing ever raises. A plain string
        # looks broken but carries str.index, so it slips through harmlessly —
        # which is exactly how this test first passed against an except clause
        # narrowed to a type that can never occur here.
        index = 1

    ctx = QueryContext(kb_id=uuid.uuid4(), question="q")
    ctx.answer = "peu importe [1]."
    ctx.citations = [_Broken()]  # type: ignore[list-item]
    assert caution_event(ctx) is None


@pytest.mark.asyncio
async def test_the_stream_yields_the_caution_before_done():
    from tablerag.query.pipeline import QueryPipeline
    from tablerag.query.steps.generate import GenerateAnswer

    # the stream dispatches on isinstance, so the fake must really be one
    class FakeGenerate(GenerateAnswer):
        async def run(self, ctx):
            return ctx

        async def stream(self, ctx):
            ctx.answer = "Le graphique montre 27 % [1]."
            yield "Le graphique montre 27 % [1]."

    ctx = QueryContext(kb_id=uuid.uuid4(), question="q")
    ctx.citations = [_figure_citation()]
    kinds = [kind async for kind, _ in QueryPipeline([FakeGenerate()]).stream(ctx)]
    assert kinds == ["citations", "token", "caution", "done"]


def test_every_stream_consumer_handles_the_caution_event():
    """A pipeline event nobody serialises is a feature that exists only in tests.

    There are three consumers of this stream — the scoped chat route, the
    multi-KB chat route and the assistants route — and the plan for this work
    named only one of them."""
    consumers = [REPO_ROOT / "tablerag" / "api" / "routes" / "chat.py",
                 REPO_ROOT / "tablerag" / "api" / "routes" / "assistants.py"]
    for path in consumers:
        source = path.read_text(encoding="utf-8")
        citation_branches = len(re.findall(r'kind == "citations"', source))
        caution_branches = len(re.findall(r'kind == "caution"', source))
        assert citation_branches == caution_branches, (
            f"{path.name} handles the citations event {citation_branches} "
            f"time(s) but the caution event {caution_branches} time(s) — one of "
            f"its streams would silently never warn the reader")


def test_the_verify_step_result_reaches_the_caution():
    # caution_for reads it, but only if the pipeline hands it over: the field
    # existed on QueryContext and was passed to nothing.
    ctx = QueryContext(kb_id=uuid.uuid4(), question="q")
    ctx.answer = "Le taux est de 4,79 % [1]."
    ctx.citations = [Citation(index=1, kind="table", doc_id=uuid.uuid4(),
                              filename="f.pdf", page=1,
                              element_id=uuid.uuid4(), snippet="", score=0.9,
                              confidence=1.0)]
    ctx.verification = {"enabled": True, "status": "warnings",
                        "unverified": ["4,79"]}
    event = caution_event(ctx)
    assert event is not None and event.reasons == ["unverified_numbers"]


def test_every_caution_reason_has_copy_in_the_ui():
    """A reason key with no French copy reaches the reader as nothing at all.

    CautionNotice maps reasons through CAUTION_COPY and drops what it cannot
    translate; when none survive it returns null. So a caution that fired
    correctly in the pipeline - the answer DOES rest on something shaky -
    renders as blank space, which is indistinguishable from a clean answer.
    Adding a reason and forgetting the copy is a silent regression, so it is
    pinned here rather than left to be noticed."""
    reasons = set(re.findall(
        r'reasons\.append\("([a-z_]+)"\)',
        (REPO_ROOT / "tablerag" / "core" / "citations.py").read_text(
            encoding="utf-8")))
    panel = (REPO_ROOT / "frontend" / "components" / "ChatPanel.tsx").read_text(
        encoding="utf-8")
    block = panel[panel.index("CAUTION_COPY"):]
    block = block[:block.index("};")]
    translated = set(re.findall(r"^\s{2}([a-z_]+):", block, re.M))
    assert reasons, "the reason keys are no longer written as literals here"
    assert reasons <= translated, \
        f"caution reasons with no copy in ChatPanel: {sorted(reasons - translated)}"
