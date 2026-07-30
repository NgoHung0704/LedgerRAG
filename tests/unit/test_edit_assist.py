"""The in-editor editing assistant.

It rewrites content the reviewer already has. The rule that matters is that it
may REARRANGE but never ADD: a rewrite that quietly invents a figure would
poison the records answers quote numbers from, and would look plausible doing
it. Nothing it returns is applied automatically.
"""

from tablerag.models.edit_assist import (
    FORMATS,
    SYSTEM_PROMPT,
    assist,
    build_user_message,
    split_reply,
)


# --- the contract -----------------------------------------------------------

def test_the_prompt_forbids_inventing_anything():
    assert "Never invent" in SYSTEM_PROMPT
    assert "may NOT add facts" in SYSTEM_PROMPT
    # and it must refuse rather than fill a gap
    assert "instead of filling the gap" in SYSTEM_PROMPT


def test_the_prompt_asks_for_the_complete_new_version():
    assert "COMPLETE new version in ONE fenced code block" in SYSTEM_PROMPT


def test_every_editable_pane_has_a_description():
    assert set(FORMATS) == {"html", "text", "records", "summary"}


def test_user_message_carries_the_content_and_the_instruction():
    msg = build_user_message("html", "<table><tr><td>16</td></tr></table>",
                             "supprime la colonne vide")
    assert "an HTML table" in msg
    assert "<td>16</td>" in msg
    assert "supprime la colonne vide" in msg


# --- reading the reply ------------------------------------------------------

def test_a_fenced_block_becomes_the_proposal():
    prose, proposal = split_reply(
        "J'ai retiré la colonne vide.\n\n```html\n<table><tr><td>16</td></tr>"
        "</table>\n```\n")
    assert prose == "J'ai retiré la colonne vide."
    assert proposal == "<table><tr><td>16</td></tr></table>"


def test_an_untagged_block_works_too():
    _, proposal = split_reply("ok\n```\nline one\nline two\n```")
    assert proposal == "line one\nline two"


def test_a_plain_answer_proposes_nothing():
    """A question deserves an answer, not a rewrite to apply."""
    prose, proposal = split_reply("La deuxième ligne n'a pas d'en-tête.")
    assert proposal is None
    assert prose == "La deuxième ligne n'a pas d'en-tête."


def test_only_the_first_block_is_taken():
    _, proposal = split_reply("a\n```\nfirst\n```\nb\n```\nsecond\n```")
    assert proposal == "first"


def test_a_block_with_no_prose_still_reads():
    prose, proposal = split_reply("```html\n<table/>\n```")
    assert proposal == "<table/>"
    assert prose  # never an empty bubble


def test_empty_reply_is_harmless():
    assert split_reply("") == ("", None)


# --- the call ---------------------------------------------------------------

async def test_assist_passes_history_and_returns_the_split(monkeypatch):
    seen: dict = {}

    class P:
        async def chat(self, messages, stream=True, temperature=None, options=None):
            seen["messages"] = messages
            yield "voilà\n```html\n<table/>\n```"

    monkeypatch.setattr("tablerag.models.edit_assist.get_provider",
                        lambda role: P())
    reply, proposal = await assist(
        "html", "<table><tr/></table>", "enlève la ligne vide",
        history=[("user", "et l'en-tête ?"), ("assistant", "il est correct")])

    assert reply == "voilà"
    assert proposal == "<table/>"
    roles = [m.role for m in seen["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert seen["messages"][-1].content.endswith("enlève la ligne vide")


async def test_assist_is_deterministic(monkeypatch):
    """An editing tool that rewrites differently each time is not trustworthy."""
    seen: dict = {}

    class P:
        async def chat(self, messages, stream=True, temperature=None, options=None):
            seen["temperature"] = temperature
            seen["options"] = options
            yield "ok"

    monkeypatch.setattr("tablerag.models.edit_assist.get_provider",
                        lambda role: P())
    await assist("text", "x", "y")
    assert seen["temperature"] == 0.0
    assert seen["options"]["temperature"] == 0.0
