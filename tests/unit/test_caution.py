import uuid

from tablerag.core.citations import caution_for, cited_indices
from tablerag.core.schemas import Citation


def _cite(index: int, **kw) -> Citation:
    base = dict(index=index, kind="text", doc_id=uuid.uuid4(),
                filename="notice.pdf", page=3, element_id=uuid.uuid4(),
                snippet="", score=0.5)
    base.update(kw)
    return Citation(**base)


def test_markers_are_read_out_of_the_answer():
    assert cited_indices("La garantie est de 100 % [1][3], voir [10].") \
        == {1, 3, 10}


def test_prose_that_merely_contains_brackets_is_not_a_citation():
    # the SHORT one matters: a marker pattern loosened to any bracketed text
    # still misses "[voir annexe]" on length alone, so a long example proves
    # nothing about whether the pattern is actually restricted to digits
    assert cited_indices("Le taux [cf] reste inchangé.") == set()
    assert cited_indices("Le taux [voir annexe] reste inchangé.") == set()


def test_a_cited_figure_always_raises_a_caution():
    caution = caution_for("Le graphique montre 27 % [1].",
                          [_cite(1, from_figure=True)], contact=None)
    assert caution is not None
    assert caution.reasons == ["figure_reading"]


def test_a_cited_low_confidence_source_raises_one():
    caution = caution_for("La valeur est 34 900 [1].",
                          [_cite(1, confidence=0.4)], contact=None)
    assert caution is not None
    assert caution.reasons == ["low_confidence"]


def test_a_cited_source_flagged_for_review_raises_one():
    caution = caution_for("La valeur est 34 900 [1].",
                          [_cite(1, needs_review=True)], contact=None)
    assert caution is not None
    assert caution.reasons == ["needs_review"]


def test_a_clean_cited_source_raises_nothing():
    # the caution must stay silent on an ordinary answer, or it becomes noise
    # the reader learns to skip past
    assert caution_for("La valeur est 34 900 [1].",
                       [_cite(1, confidence=1.0)], contact=None) is None


def test_an_uncited_figure_does_not():
    caution = caution_for("La valeur est 34 900 [1].",
                          [_cite(1, confidence=1.0),
                           _cite(2, from_figure=True)], contact=None)
    assert caution is None


def test_the_contact_is_carried_through_when_the_kb_sets_one():
    caution = caution_for("Voir le graphique [1].",
                          [_cite(1, from_figure=True)],
                          contact="service RH du CETIAT")
    assert caution.contact == "service RH du CETIAT"


def test_with_no_markers_at_all_the_offered_sources_are_judged():
    # an answer citing nothing is the case where we know LEAST about where it
    # came from, so it is judged on everything it was shown
    caution = caution_for("La valeur n'est pas dans les documents.",
                          [_cite(1, from_figure=True)], contact=None)
    assert caution is not None


def test_several_reasons_are_all_reported():
    caution = caution_for("Le graphique montre 27 % [1][2].",
                          [_cite(1, from_figure=True),
                           _cite(2, needs_review=True, confidence=0.2)],
                          contact=None)
    assert set(caution.reasons) == {"figure_reading", "needs_review",
                                    "low_confidence"}


def test_a_confidence_exactly_at_the_threshold_is_not_flagged():
    # the threshold is "below 0.9", not "at or below": confidence_review_threshold
    # is the value the ingestion side already treats as acceptable
    assert caution_for("La valeur est 34 900 [1].",
                       [_cite(1, confidence=0.9)], contact=None) is None


# --- the strongest signal was the one not wired in ---------------------------
# verify_answer already reads every number out of the answer and tries to match
# it against the numbers in the retrieved sources. A number it cannot match is
# the single most concrete thing this system knows about an answer being shaky,
# and it was rendered as a separate badge while the caution - the field that
# carries "check the original, or ask HR" - stayed silent about it.


def test_a_number_that_matched_no_source_raises_a_caution():
    caution = caution_for("Le taux est de 4,79 % [1].",
                          [_cite(1, confidence=1.0)], contact=None,
                          verification={"enabled": True, "status": "warnings",
                                        "unverified": ["4,79"]})
    assert caution is not None
    assert caution.reasons == ["unverified_numbers"]


def test_verification_that_matched_everything_stays_silent():
    assert caution_for("Le taux est de 4,79 % [1].",
                       [_cite(1, confidence=1.0)], contact=None,
                       verification={"enabled": True, "status": "ok",
                                     "numbers": [{"raw": "4,79", "value": 4.79,
                                                  "status": "verified"}],
                                     "unverified": []}) is None


def test_verification_switched_off_is_not_read_as_a_clean_bill():
    # absence of evidence is not evidence: a KB with verify disabled must not
    # look SAFER than one where the check ran and passed
    assert caution_for("Le taux est de 4,79 % [1].",
                       [_cite(1, confidence=1.0)], contact=None,
                       verification={"enabled": False, "status": "ok",
                                     "unverified": []}) is None
    assert caution_for("Le taux est de 4,79 % [1].",
                       [_cite(1, confidence=1.0)], contact=None,
                       verification=None) is None


def test_an_unmatched_number_is_reported_beside_the_other_reasons():
    caution = caution_for("Le graphique montre 27 % [1].",
                          [_cite(1, from_figure=True)], contact=None,
                          verification={"enabled": True, "status": "warnings",
                                        "unverified": ["27"]})
    assert set(caution.reasons) == {"figure_reading", "unverified_numbers"}


# --- what the answer actually rests on, for the "see also" list --------------


def test_the_pages_an_answer_rests_on_are_the_ones_it_cited():
    from tablerag.core.citations import pages_used

    doc = uuid.uuid4()
    other = uuid.uuid4()
    cites = [_cite(1, doc_id=doc, page=3), _cite(2, doc_id=doc, page=7),
             _cite(3, doc_id=other, page=2)]
    assert pages_used("La valeur est 34 900 [1], voir aussi [3].", cites) \
        == {(doc, 3), (other, 2)}


def test_an_answer_citing_nothing_rests_on_every_page_it_was_shown():
    # the same rule caution_for uses: with no markers we know LEAST about where
    # the answer came from, so nothing is excluded
    from tablerag.core.citations import pages_used

    doc = uuid.uuid4()
    cites = [_cite(1, doc_id=doc, page=3), _cite(2, doc_id=doc, page=7)]
    assert pages_used("Cette information ne figure pas dans les documents.",
                      cites) == {(doc, 3), (doc, 7)}


def test_two_citations_on_one_page_are_one_page():
    from tablerag.core.citations import pages_used

    doc = uuid.uuid4()
    assert pages_used("[1][2]", [_cite(1, doc_id=doc, page=3),
                                 _cite(2, doc_id=doc, page=3)]) == {(doc, 3)}
