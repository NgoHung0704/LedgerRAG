"""Multi-turn: CondenseQuestion rewrites a follow-up into a standalone query.

The retrieval/routing path acts on text alone, so a fragment like "et pour la
classe II ?" must be folded with the thread before it is searched. Guardrails:
no history is a pure passthrough (single-turn evals cannot regress), and any
failure or runaway reply falls back to the raw question."""

import uuid

import pytest

from tablerag.query.pipeline import QueryContext
from tablerag.query.steps.condense import (
    CondenseQuestion,
    build_condense_prompt,
)


def _ctx(**over):
    base = dict(kb_id=uuid.uuid4(), question="q")
    base.update(over)
    return QueryContext(**base)


def _fake_chat(reply):
    class P:
        async def chat(self, messages, stream=True, temperature=None, options=None):
            for tok in reply:
                yield tok
    return P()


# --- passthrough: no history means no LLM call and no rewrite ----------------

async def test_no_history_is_pure_passthrough(monkeypatch):
    monkeypatch.setattr(
        "tablerag.models.registry.get_provider",
        lambda role: pytest.fail("condense must not call the model without history"))
    ctx = _ctx(question="Quel est le salaire de la classe I ?")
    await CondenseQuestion().run(ctx)
    assert ctx.search_question == ctx.question
    assert ctx.search_query == ctx.question


# --- the real job: a fragment becomes standalone -----------------------------

async def test_follow_up_is_rewritten(monkeypatch):
    standalone = "Quel est le salaire de la classe II en 2023 ?"
    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: _fake_chat([standalone]))
    ctx = _ctx(
        question="et pour la classe II ?",
        history=[
            ("user", "Quel est le salaire de la classe I en 2023 ?"),
            ("assistant", "La classe I gagne 34 900 € [1]."),
        ],
    )
    await CondenseQuestion().run(ctx)
    assert ctx.search_query == standalone


async def test_rewrite_is_stripped_of_quotes(monkeypatch):
    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: _fake_chat(['  "salaire classe II 2023"  ']))
    ctx = _ctx(question="et la II ?", history=[("user", "salaire classe I ?")])
    await CondenseQuestion().run(ctx)
    assert ctx.search_query == "salaire classe II 2023"


# --- guardrails: never let condensing break or hijack the search -------------

async def test_runaway_reply_falls_back_to_raw(monkeypatch):
    # the model started answering instead of condensing -> ignore it
    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: _fake_chat(["x" * 500]))
    ctx = _ctx(question="et pour la II ?", history=[("user", "salaire I ?")])
    await CondenseQuestion().run(ctx)
    assert ctx.search_query == "et pour la II ?"


async def test_empty_reply_falls_back_to_raw(monkeypatch):
    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: _fake_chat(["   "]))
    ctx = _ctx(question="et pour la II ?", history=[("user", "salaire I ?")])
    await CondenseQuestion().run(ctx)
    assert ctx.search_query == "et pour la II ?"


async def test_model_failure_falls_back_to_raw(monkeypatch):
    class Boom:
        async def chat(self, *a, **k):
            raise RuntimeError("model down")
            yield  # pragma: no cover

    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: Boom())
    ctx = _ctx(question="et pour la II ?", history=[("user", "salaire I ?")])
    await CondenseQuestion().run(ctx)
    assert ctx.search_query == "et pour la II ?"


# --- prompt shape ------------------------------------------------------------

def test_prompt_carries_thread_and_latest_message():
    p = build_condense_prompt(
        [("user", "Salaire classe I ?"), ("assistant", "34 900 €")],
        "et pour la II ?")
    assert "User: Salaire classe I ?" in p
    assert "Assistant: 34 900 €" in p
    assert "Latest message: et pour la II ?" in p


def test_prompt_trims_long_turns():
    p = build_condense_prompt([("assistant", "A" * 1000)], "et après ?")
    assert "…" in p
    assert "A" * 1000 not in p
