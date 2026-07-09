"""Phase 4 answer-number verification: extraction, matching, arithmetic
whitelist, and the Verify step no-op contract."""

import pytest

from tablerag.query.verification import extract_numbers, verify_answer

SOURCES_FR = [
    "Afrique | Algérie | Citadine | 2013 T1 janvier | 7 462 639 € | volume 426",
    "Charges sociales: 365 580 €. Salaires: 812 400 €.",
]


def test_extract_numbers_fr_locale():
    nums = dict(extract_numbers("Le chiffre est 7 462 639 € et 12,5 %.", "fr"))
    assert 7462639.0 in nums.values()
    assert 12.5 in nums.values()


def test_verified_number_from_source():
    result = verify_answer(
        "Le chiffre d'affaires est de 7 462 639 € pour janvier.",
        SOURCES_FR, "fr")
    assert result.status == "ok"
    assert all(n.status == "verified" for n in result.numbers if n.value == 7462639.0)
    assert result.unverified == []


def test_unverified_number_flagged():
    result = verify_answer(
        "Le chiffre d'affaires est de 9 999 999 €.", SOURCES_FR, "fr")
    assert result.status == "warnings"
    assert any("9 999 999" in u for u in result.unverified)


def test_computed_sum_is_whitelisted():
    """Salaires + Charges = 812400 + 365580 = 1 177 980 — the LLM did the math."""
    result = verify_answer(
        "Le total salaires plus charges est 1 177 980 €.", SOURCES_FR, "fr")
    total = next(n for n in result.numbers if n.value == 1177980.0)
    assert total.status == "computed"
    assert result.status == "ok"


def test_percentage_share_is_whitelisted():
    sources = ["Region A: 60. Region B: 40."]
    result = verify_answer("Region A represents 60 % of the total.", sources, "en")
    share = next(n for n in result.numbers if n.value == 60.0)
    assert share.status in ("verified", "computed")


def test_disabled_verify_is_pure_noop():
    import asyncio
    import uuid

    from tablerag.query.pipeline import QueryContext, SourceBlock
    from tablerag.query.steps.verify import Verify

    ctx = QueryContext(kb_id=uuid.uuid4(), question="q", locale="fr")
    ctx.answer = "7 462 639 €"
    ctx.sources = [SourceBlock(
        kind="table", doc_id=uuid.uuid4(), filename="f.pdf", page=1,
        element_id=uuid.uuid4(), content="autre", snippet="", score=1.0)]
    result = asyncio.run(Verify(enabled=False).run(ctx))
    assert result is ctx
    assert ctx.verification is None


def test_enabled_verify_populates_context():
    import asyncio
    import uuid

    from tablerag.query.pipeline import QueryContext, SourceBlock
    from tablerag.query.steps.verify import Verify

    ctx = QueryContext(kb_id=uuid.uuid4(), question="q", locale="fr")
    ctx.answer = "Le montant est 7 462 639 €."
    ctx.sources = [SourceBlock(
        kind="table", doc_id=uuid.uuid4(), filename="f.pdf", page=1,
        element_id=uuid.uuid4(), content=SOURCES_FR[0], snippet="", score=1.0)]
    asyncio.run(Verify(enabled=True).run(ctx))
    assert ctx.verification["enabled"] is True
    assert ctx.verification["status"] == "ok"


@pytest.mark.parametrize("locale,answer,source", [
    ("de", "Der Umsatz beträgt 7.462.639,50 €.", "Umsatz: 7.462.639,50 €"),
    ("en", "Revenue was $7,462,639.50.", "Revenue: $7,462,639.50"),
])
def test_verification_is_locale_aware(locale, answer, source):
    result = verify_answer(answer, [source], locale)
    assert result.status == "ok"
    assert result.unverified == []
