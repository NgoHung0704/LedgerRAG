"""A knowledge base that declares a language binds what the models WRITE.

Measured on the deployment box before this: every figure description of a
FRENCH factsheet came back in English — "Bar chart showing sector distribution"
for a chart titled « Répartition sectorielle ». A description in the wrong
language is nearly unfindable, because the question and the chunk share no
words.

The model chooses for itself in exactly one case: the KB declares nothing.
"""

import pytest

from tablerag.ingestion.ocr import REREAD_MODES, language_line


def test_a_declared_language_is_binding():
    line = language_line("fr", "the description")
    assert "in French" in line
    assert "even if the page is in another language" in line


def test_it_still_forbids_translating_what_is_copied():
    """The rule is about prose the model writes. Ordering French output must
    not become an order to translate a quoted label, a value or a name — every
    prompt here forbids that, and this one must not undo it."""
    assert "never translate what you are COPYING" in language_line("fr", "x")


def test_nothing_declared_means_the_page_decides():
    """The one honest alternative. Not "whatever the model feels like": the
    words printed on the page."""
    line = language_line(None, "the explanation")
    assert "same language as the words printed on the page" in line
    assert "French" not in line


@pytest.mark.parametrize("what", ["the description", "the explanation"])
def test_the_rule_names_what_it_governs(what):
    assert f"Write {what} in French" in language_line("fr", what)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,bound", [
    ("summary", True),      # prose the model writes
    ("both", True),         # transcription + a written reading
    ("structure", False),   # a COPY of the page
])
async def test_only_what_the_model_writes_carries_the_language_rule(
        monkeypatch, mode, bound):
    """A transcription copies the page. Telling it to produce French from a
    German page would be ordering a translation — the one thing every prompt
    here forbids — so `structure` is left alone."""
    from tablerag.ingestion import ocr

    seen = {}

    async def fake(image, prompt):
        seen["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(ocr, "_transcribe", fake)
    await ocr.reread_page(b"png", mode, "fr")
    assert ("Write the explanation in French" in seen["prompt"]) is bound
    # the mode's own prompt is always there, untouched
    assert REREAD_MODES[mode] in seen["prompt"]


@pytest.mark.asyncio
async def test_a_figure_description_obeys_the_declared_language(monkeypatch):
    from tablerag.ingestion import ocr

    seen = {}

    async def fake(image, prompt):
        seen["prompt"] = prompt
        return "x\nINFORMATIVE: yes"

    monkeypatch.setattr(ocr, "_transcribe", fake)
    await ocr.describe_figure(b"png", locale="fr")
    assert "Write the description in French" in seen["prompt"]


def test_a_table_summary_obeys_it_too():
    from tablerag.ingestion.table_pipeline import build_summary_prompt

    assert "in French ONLY" in build_summary_prompt("<table></table>", "fr")
    assert "dominant language of the table content" in build_summary_prompt(
        "<table></table>", None)
