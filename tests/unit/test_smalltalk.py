"""Small talk is answered as small talk, never as a failed search.

The asymmetry that shapes these tests: answering a greeting with "no relevant
passages" is a wart, but misreading a REAL question as small talk would refuse
to search the documents at all. So the load-bearing tests are the negative ones
— every question in the eval sets, and every greeting-prefixed real question,
must go to retrieval.
"""

import json
import uuid
from pathlib import Path

import pytest

from tablerag.query.pipeline import QueryContext
from tablerag.query.steps.smalltalk import SmallTalk, classify_smalltalk

QA_DIR = Path(__file__).resolve().parents[1] / "eval" / "qa"


def _ctx(question: str, **over) -> QueryContext:
    return QueryContext(kb_id=uuid.uuid4(), question=question, **over)


def _fake_chat(reply):
    class P:
        async def chat(self, messages, stream=True, temperature=None, options=None):
            for tok in reply:
                yield tok
    return P()


# --- positive: real conversational messages ---------------------------------

@pytest.mark.parametrize("message,kind", [
    ("Salut", "greeting"),
    ("Bonjour !", "greeting"),
    ("bonsoir", "greeting"),
    ("Coucou :)", "greeting"),
    ("Hello", "greeting"),
    ("hi there", None),          # "there" is not in the vocabulary -> retrieval
    ("Xin chào", "greeting"),
    ("Merci beaucoup !", "thanks"),
    ("merci", "thanks"),
    ("Thanks a lot", None),      # "lot" not in vocabulary -> retrieval
    ("thank you", "thanks"),
    ("Cảm ơn bạn", "thanks"),
    ("Au revoir", "bye"),
    ("bye", "bye"),
    ("Ça va ?", "howareyou"),
    ("comment ça va ?", "howareyou"),
    ("how are you", "howareyou"),
    ("ok", "ack"),
    ("D'accord, merci", "thanks"),   # both conversational
    ("Qui es-tu ?", "capability"),
    ("Que peux-tu faire ?", "capability"),
    ("what can you do", "capability"),
    ("bạn là ai", "capability"),
])
def test_conversational_messages_are_detected(message, kind):
    match = classify_smalltalk(message)
    if kind is None:
        assert match is None, f"{message!r} must go to retrieval"
    else:
        assert match is not None, f"{message!r} should be small talk"
        assert match.kind == kind


def test_language_is_carried_for_the_fallback_reply():
    assert classify_smalltalk("Bonjour").language == "fr"
    assert classify_smalltalk("hello").language == "en"
    assert classify_smalltalk("xin chào").language == "vi"


# --- negative: the expensive mistake ----------------------------------------

def _eval_questions() -> list[str]:
    out: list[str] = []
    for name in ("questions.jsonl", "routing.jsonl"):
        for line in (QA_DIR / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line)["question"])
    for line in (QA_DIR / "followups.jsonl").read_text(
            encoding="utf-8").splitlines():
        if line.strip():
            out.extend(t["question"] for t in json.loads(line)["turns"])
    return out


@pytest.mark.parametrize("question", _eval_questions())
def test_no_eval_question_is_ever_small_talk(question):
    """The measured gates must be untouched: if any of these classified as
    small talk it would never reach retrieval."""
    assert classify_smalltalk(question) is None


@pytest.mark.parametrize("question", [
    # a greeting glued to a real question is a real question
    "Bonjour, quel est le salaire de la classe 11 ?",
    "Salut ! cotation du poste Comptable ?",
    "Merci de me donner le barème unique",
    "hello, what is the minimum wage for class 16?",
    # short document questions must survive
    "cotation Comptable ?",
    "classe 16 ?",
    "et pour la classe II ?",
    "barème F",
    # digits alone rule it out
    "16",
])
def test_real_questions_go_to_retrieval(question):
    assert classify_smalltalk(question) is None


# --- the step ---------------------------------------------------------------

async def test_step_short_circuits_and_answers(monkeypatch):
    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: _fake_chat(["Bonjour ! ", "Posez votre question."]))
    ctx = _ctx("Salut")
    tokens = [t async for t in SmallTalk().stream(ctx)]
    assert ctx.short_circuit is True
    assert "".join(tokens) == ctx.answer == "Bonjour ! Posez votre question."


async def test_step_is_a_no_op_on_a_real_question(monkeypatch):
    monkeypatch.setattr(
        "tablerag.models.registry.get_provider",
        lambda role: pytest.fail("a real question must not hit the small-talk model"))
    ctx = _ctx("Quelle est la cotation du poste Comptable ?")
    assert [t async for t in SmallTalk().stream(ctx)] == []
    assert ctx.short_circuit is False
    assert ctx.answer == ""


async def test_model_failure_still_greets(monkeypatch):
    class Boom:
        async def chat(self, *a, **k):
            raise RuntimeError("model down")
            yield  # pragma: no cover

    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: Boom())
    ctx = _ctx("Bonjour")
    tokens = [t async for t in SmallTalk().stream(ctx)]
    assert ctx.short_circuit is True
    assert "documents" in "".join(tokens)  # the canned French fallback


async def test_disabled_by_config(monkeypatch):
    from tablerag.core.config import get_settings

    monkeypatch.setattr(
        "tablerag.models.registry.get_provider",
        lambda role: pytest.fail("small talk is disabled; nothing should run"))
    settings = get_settings()
    monkeypatch.setattr(settings, "smalltalk_enabled", False)
    monkeypatch.setattr("tablerag.core.config.get_settings", lambda: settings)
    ctx = _ctx("Salut")
    assert [t async for t in SmallTalk().stream(ctx)] == []
    assert ctx.short_circuit is False


async def test_pipeline_skips_retrieval_on_small_talk(monkeypatch):
    """End-to-end shape: a greeting must not reach the router or retrieval."""
    from tablerag.query.pipeline import QueryPipeline

    class Exploding:
        async def run(self, ctx):
            pytest.fail("retrieval must not run for small talk")

    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: _fake_chat(["Bonjour !"]))
    pipeline = QueryPipeline([SmallTalk(), Exploding()])
    ctx = _ctx("Salut")
    events = [(kind, payload) async for kind, payload in pipeline.stream(ctx)]
    assert [k for k, _ in events] == ["token", "done"]
    assert ctx.answer == "Bonjour !"
    assert ctx.citations == [] and ctx.verification is None
