"""Phase 5 routing: LLMRouter picks KB(s); routing is the known dead end, so
a manual pin always wins and any failure degrades to ALL KBs, never none."""

import uuid

import pytest

from tablerag.query.pipeline import QueryContext
from tablerag.query.steps.router import (
    KBRef,
    LLMRouter,
    SingleKBRouter,
    build_router_prompt,
    parse_router_choice,
)

KBS = [
    KBRef(uuid.uuid4(), "Règlement intérieur", "Politiques RH, congés, discipline"),
    KBRef(uuid.uuid4(), "Rémunération", "Grilles de salaire, primes, cotisations"),
    KBRef(uuid.uuid4(), "Formation", "Catalogue de formations et parcours"),
]


def _ctx(**over):
    base = dict(kb_id=uuid.uuid4(), question="q")
    base.update(over)
    return QueryContext(**base)


def _kbs_fn(kbs=KBS):
    async def fn():
        return kbs
    return fn


def _fake_chat(reply):
    class P:
        async def chat(self, messages, stream=True, temperature=None, options=None):
            for tok in reply:
                yield tok
    return P()


# --- parse_router_choice ----------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("[1]", [0]),
    ("[2, 3]", [1, 2]),
    ("Sure: [1,2] are relevant.", [0, 1]),   # array embedded in prose
    ("[1,1,2]", [0, 1]),                      # dedupe, keep order
    ("[9]", []),                              # out of range dropped
    ("[3,1]", [2, 0]),                        # order preserved as written
    ("no array here", []),
    ("[not json]", []),
    ("[]", []),
    ('{"kb": 1}', []),                        # object, not array
])
def test_parse_router_choice(text, expected):
    assert parse_router_choice(text, n=3) == expected


def test_prompt_lists_names_and_descriptions():
    p = build_router_prompt("Combien de jours de congés ?", KBS)
    assert "1. Règlement intérieur — Politiques RH" in p
    assert "2. Rémunération" in p and "3. Formation" in p
    assert "Combien de jours de congés" in p


# --- SingleKBRouter ---------------------------------------------------------

async def test_single_kb_router_records_mode():
    ctx = _ctx()
    await SingleKBRouter().run(ctx)
    assert ctx.routed_kb_ids == [ctx.kb_id]
    assert ctx.routing == {"mode": "single", "kb_ids": [str(ctx.kb_id)]}


# --- LLMRouter --------------------------------------------------------------

async def test_pinned_override_skips_the_llm(monkeypatch):
    monkeypatch.setattr(
        "tablerag.models.registry.get_provider",
        lambda role: pytest.fail("pinned routing must not call the model"))
    pinned = [KBS[0].id, KBS[2].id]
    ctx = _ctx(pinned_kb_ids=pinned)
    await LLMRouter(list_kbs_fn=_kbs_fn()).run(ctx)
    assert ctx.routed_kb_ids == pinned
    assert ctx.routing["mode"] == "pinned"


async def test_single_kb_is_trivial_no_llm(monkeypatch):
    monkeypatch.setattr(
        "tablerag.models.registry.get_provider",
        lambda role: pytest.fail("one KB needs no routing decision"))
    ctx = _ctx()
    await LLMRouter(list_kbs_fn=_kbs_fn([KBS[0]])).run(ctx)
    assert ctx.routed_kb_ids == [KBS[0].id]
    assert ctx.routing["mode"] == "trivial"


async def test_llm_selects_multiple(monkeypatch):
    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: _fake_chat(["[2", ", 3]"]))
    ctx = _ctx(question="Prime de formation et salaire ?")
    await LLMRouter(list_kbs_fn=_kbs_fn()).run(ctx)
    assert ctx.routed_kb_ids == [KBS[1].id, KBS[2].id]
    assert ctx.routing["mode"] == "llm"
    assert ctx.routing["names"] == ["Rémunération", "Formation"]


async def test_empty_pick_degrades_to_all(monkeypatch):
    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: _fake_chat(["hmm not sure"]))
    ctx = _ctx()
    await LLMRouter(list_kbs_fn=_kbs_fn()).run(ctx)
    assert ctx.routed_kb_ids == [kb.id for kb in KBS]   # all, never none
    assert ctx.routing["mode"] == "fallback_all"


async def test_model_failure_degrades_to_all(monkeypatch):
    class Boom:
        async def chat(self, *a, **k):
            raise RuntimeError("model down")
            yield  # pragma: no cover

    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: Boom())
    ctx = _ctx()
    await LLMRouter(list_kbs_fn=_kbs_fn()).run(ctx)
    assert ctx.routed_kb_ids == [kb.id for kb in KBS]
    assert ctx.routing["mode"] == "fallback_all"


# --- routing eval grader (SPEC Phase 5 §4: score routing separately) --------

def test_grade_routing_exact_match():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval" / "qa"))
    from run_eval_routing import grade_routing

    recall, exact, _ = grade_routing(["Rémunération"], ["Rémunération"])
    assert recall and exact


def test_grade_routing_substring_and_over_selection():
    from run_eval_routing import grade_routing

    # loose name in the question matches the full KB name (recall ok)...
    recall, exact, detail = grade_routing(
        ["Règlement"], ["Règlement intérieur", "Formation"])
    assert recall and not exact           # extra KB -> not exact, still reachable
    assert "over-selected" in detail


def test_grade_routing_miss_is_fatal():
    from run_eval_routing import grade_routing

    recall, exact, detail = grade_routing(["Rémunération"], ["Formation"])
    assert not recall and not exact
    assert "MISSED" in detail


def test_grade_routing_multi_expected():
    from run_eval_routing import grade_routing

    recall, exact, _ = grade_routing(
        ["Rémunération", "Formation"], ["Formation", "Rémunération"])
    assert recall and exact               # order-independent set match
