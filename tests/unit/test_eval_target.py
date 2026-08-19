"""Which endpoint an eval run talks to.

The gates have always asked a KNOWLEDGE BASE. What a colleague actually types
into is an ASSISTANT, which carries its own instructions, its own escalation
contact, its own verify override and its own set of knowledge bases — none of
which the KB endpoint loads. A score measured through the KB says nothing about
the thing people use.

The choice is a pure function in each harness precisely so this test cannot
re-implement it: an earlier lesson in this repo was a test that inlined the
lookup it was checking, so breaking the real one left it green.

The two harnesses choose differently, which is why there is no shared helper:
run_eval_qa asks ONE knowledge base, run_eval_followup asks the multi-KB
endpoint so its condense step has something to condense.
"""

import importlib.util
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name, REPO / "tests" / "eval" / "qa" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def qa():
    return _load("run_eval_qa")


@pytest.fixture(scope="module")
def followup():
    return _load("run_eval_followup")


# --- run_eval_qa: one KB, or one assistant ---------------------------------

def test_a_kb_is_asked_on_the_kb_endpoint(qa):
    assert qa.chat_url("kb-123", None) == "/api/kbs/kb-123/chat"


def test_an_assistant_is_asked_on_its_own_endpoint(qa):
    assert qa.chat_url(None, "as-456") == "/api/assistants/as-456/chat"


def test_naming_both_is_refused(qa):
    # silently preferring one would make the report name a target that was
    # never asked
    with pytest.raises(ValueError):
        qa.chat_url("kb-123", "as-456")


def test_naming_neither_is_refused(qa):
    with pytest.raises(ValueError):
        qa.chat_url(None, None)


# --- run_eval_followup: the multi-KB endpoint, or one assistant ------------

def test_followup_defaults_to_the_multi_kb_endpoint(followup):
    assert followup.chat_url(None) == "/api/chat"


def test_followup_against_an_assistant_uses_the_assistant_endpoint(followup):
    assert followup.chat_url("as-456") == "/api/assistants/as-456/chat"


def test_an_assistant_cannot_have_its_knowledge_bases_pinned(followup):
    """AssistantChatRequest has no kb_ids field, and that is not an oversight:
    an assistant's scope IS its attached set. Sending pins would be silently
    dropped by the API, so the harness must not pretend it held routing
    constant when it did not."""
    assert followup.pins_allowed(assistant=None) is True
    assert followup.pins_allowed(assistant="as-456") is False
