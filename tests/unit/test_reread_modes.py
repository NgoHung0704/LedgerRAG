"""Re-reading a page: what the operator can ask the VLM for.

A layout-heavy page (a slide, a process diagram) sometimes needs a faithful
transcription, sometimes an explanation of what it conveys, sometimes both.
Whatever the mode, the output goes into a TEXT element — which is embedded for
retrieval and rendered as markdown — so it must stay markdown, never HTML.
"""

import pytest

from tablerag.ingestion.ocr import REREAD_MODES, reread_page


def test_the_three_modes_exist():
    assert set(REREAD_MODES) == {"structure", "summary", "both"}


def test_structure_asks_for_a_table_and_forbids_summarising():
    p = REREAD_MODES["structure"]
    assert "MARKDOWN TABLE" in p
    assert "EXACTLY as printed" in p
    assert "Never translate, summarize" in p


def test_summary_makes_relations_explicit_and_stays_on_the_page():
    p = REREAD_MODES["summary"]
    assert "relationships EXPLICIT" in p
    # the honesty line: a reading of the page, never knowledge from elsewhere
    assert "Never add knowledge from elsewhere" in p
    assert "EXACTLY as printed" in p


def test_both_keeps_the_transcription_and_appends_a_reading():
    p = REREAD_MODES["both"]
    assert "MARKDOWN TABLE" in p          # the transcription rules survive
    assert "Ce que dit cette page" in p   # and a short reading follows
    # the replace() must actually have fired, not silently left the original
    assert "Output only the transcription — no preamble" not in p


@pytest.mark.parametrize("mode", sorted(REREAD_MODES))
def test_no_mode_ever_asks_for_html(mode):
    """HTML in a text element would be embedded with its tags and shown as
    literal `<table>` in answers (the chat renders markdown, without rehype-raw)."""
    assert "HTML" not in REREAD_MODES[mode]


async def test_reread_page_uses_the_requested_prompt(monkeypatch):
    seen: list[str] = []

    class P:
        async def chat(self, messages, stream=True, temperature=None, options=None):
            seen.append(messages[0].content)
            yield "ok"

    # ocr.py imports get_provider at module level, so the name to patch is the
    # one bound there — patching the registry would leave this module untouched
    monkeypatch.setattr("tablerag.ingestion.ocr.get_provider", lambda role: P())
    assert await reread_page(b"img", "summary") == "ok"
    # the mode's prompt is what is sent. It is no longer the WHOLE prompt: a KB
    # that declares a language binds the explanation the model writes, and that
    # rule is appended (see test_declared_language.py)
    assert seen[0].startswith(REREAD_MODES["summary"])
    assert len(seen) == 1


async def test_unknown_mode_is_a_programming_error_not_a_silent_default():
    with pytest.raises(KeyError):
        await reread_page(b"img", "html")
