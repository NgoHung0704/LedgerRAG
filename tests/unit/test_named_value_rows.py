"""Rows a question names by VALUE, found without asking an embedding.

"Citez deux emplois de la classe d'emploi 10" is a filter, not a similarity
question: it wants every row whose `classe` is 10. Dense vectors cannot do that
— `classe: 10` and `classe: 11` embed almost identically, and every row of one
table shares its filename, heading and column names — so no record ranked, the
assistant read the flattened grid instead, and named two jobs from the wrong
class. Measured on the box: rows=0 gave a wrong answer, rows=1 twenty-five
seconds later gave the right one.

The table is already in hand when this runs, so its rows can be selected by
reading them, which is exact and needs no model.

Both halves are required — the column NAME and the VALUE — because a bare
number is everywhere in a table of gradings. "10" alone would drag in any row
with a cotation of 10, which is the look-alike problem this exists to end.
"""

import uuid

from tablerag.query.steps.assemble import rows_by_named_value


def _rec(**dimensions):
    return (uuid.uuid4(), dimensions)


def test_a_row_whose_named_column_holds_the_named_value_matches():
    row = _rec(emploi="Chargé(e) de Maintenance", classe="10", groupe="E")
    assert rows_by_named_value(
        "Citez deux emplois CETIAT de la classe d'emploi 10.", [row]) == [row[0]]


def test_every_row_with_that_value_comes_back_not_just_the_first():
    # the whole point of a filter: an answer that stops at one row is wrong in
    # a way the reader cannot see
    a = _rec(emploi="Chargé(e) de Maintenance", classe="10")
    b = _rec(emploi="Gestionnaire Parc Mesure", classe="10")
    c = _rec(emploi="Comptable", classe="7")
    got = rows_by_named_value("emplois de la classe 10", [a, b, c])
    assert got == [a[0], b[0]]


def test_a_bare_value_with_no_column_named_matches_nothing():
    # "37 à 39" is a cotation; a question mentioning 39 must not drag in the
    # row whose class happens to be 39
    row = _rec(emploi="Acheteur(se)", classe="39")
    assert rows_by_named_value("Quelle est la cotation de 39 ?", [row]) == []


def test_a_named_column_with_no_value_spoken_matches_nothing():
    row = _rec(emploi="Acheteur(se)", classe="10")
    assert rows_by_named_value("Quelles sont les classes d'emploi ?", [row]) == []


def test_ten_does_not_match_a_hundred():
    """The needle is the VALUE and the haystack is the question, so the trap
    runs this way round: a row whose class is 10 must not be dragged in by a
    question about class 100, where "10" is a substring. Written the other way
    round (value 100, question 10) the assertion passes with or without word
    boundaries and guards nothing — it did, until the boundaries were deleted
    to check."""
    row = _rec(emploi="X", classe="10")
    assert rows_by_named_value("la classe d'emploi 100", [row]) == []


def test_a_hundred_is_still_found_when_it_is_the_one_asked_for():
    row = _rec(emploi="X", classe="100")
    assert rows_by_named_value("la classe d'emploi 100", [row]) == [row[0]]


def test_accents_and_case_do_not_decide_the_answer():
    # the column is printed "Classé" in some grids and the question is typed
    # however the reader types it
    row = _rec(Classé="10", emploi="X")
    assert rows_by_named_value("CLASSE d'emploi 10", [row]) == [row[0]]


def test_a_value_made_of_words_matches_as_a_phrase():
    row = _rec(groupe="E", emploi="Gestionnaire Parc Mesure")
    assert rows_by_named_value(
        "Quel est l'emploi Gestionnaire Parc Mesure ?", [row]) == [row[0]]


def test_metrics_are_not_searched_only_dimensions():
    # metrics are the numbers an answer QUOTES; matching on them would pull a
    # row because the question mentioned a salary, not because it named a row
    row = (uuid.uuid4(), {"emploi": "X"})
    assert rows_by_named_value("un salaire de 34 900", [row]) == []


def test_nothing_in_nothing_out():
    assert rows_by_named_value("", [_rec(classe="10")]) == []
    assert rows_by_named_value("la classe 10", []) == []


# --- which rows reach the prompt, and under which budget -------------------

from tablerag.query.steps.assemble import (  # noqa: E402
    MAX_MATCHED_ROWS,
    MAX_NAMED_ROWS,
    AssembleContext,
)


def _texts(n, prefix):
    ids = [uuid.uuid4() for _ in range(n)]
    return ids, {i: f"{prefix}-{n}" for n, i in enumerate(ids)}


def test_ranked_rows_win_when_retrieval_found_any():
    ranked, ranked_texts = _texts(2, "ranked")
    named, named_texts = _texts(2, "named")
    element = uuid.uuid4()
    got, was_ranked = AssembleContext._rows_for(
        element, {element: ranked}, {element: named},
        {**ranked_texts, **named_texts})
    assert got == ["ranked-0", "ranked-1"]
    assert was_ranked is True


def test_read_rows_stand_in_only_when_nothing_ranked():
    named, named_texts = _texts(2, "named")
    element = uuid.uuid4()
    got, was_ranked = AssembleContext._rows_for(element, {}, {element: named}, named_texts)
    assert got == ["named-0", "named-1"]
    # the flag is what stops the prompt claiming these matched the question
    assert was_ranked is False


def test_a_similarity_guess_is_capped_tight():
    ranked, texts = _texts(MAX_MATCHED_ROWS + 3, "r")
    element = uuid.uuid4()
    got, was_ranked = AssembleContext._rows_for(element, {element: ranked}, {}, texts)
    assert len(got) == MAX_MATCHED_ROWS


def test_an_exact_filter_gets_the_larger_budget():
    # the whole reason MAX_NAMED_ROWS exists: capping a filter at four turns a
    # complete list into a partial one the reader cannot tell is partial
    named, texts = _texts(MAX_MATCHED_ROWS + 3, "n")
    element = uuid.uuid4()
    got, was_ranked = AssembleContext._rows_for(element, {}, {element: named}, texts)
    assert len(got) == MAX_MATCHED_ROWS + 3
    assert MAX_NAMED_ROWS > MAX_MATCHED_ROWS


def test_the_larger_budget_still_has_a_floor_under_it():
    named, texts = _texts(MAX_NAMED_ROWS + 5, "n")
    element = uuid.uuid4()
    got, _ = AssembleContext._rows_for(element, {}, {element: named}, texts)
    assert len(got) == MAX_NAMED_ROWS


def test_a_row_whose_text_never_loaded_is_skipped_not_crashed():
    ids = [uuid.uuid4(), uuid.uuid4()]
    element = uuid.uuid4()
    got, was_ranked = AssembleContext._rows_for(element, {}, {element: ids}, {ids[1]: "only"})
    assert got == ["only"]


# --- what the prompt CLAIMS about those rows --------------------------------
#
# The regression this section exists for: read rows were injected under the
# heading ranked rows already used, "Rows matching the question". For rows
# chosen by a string match that sentence is false, and the model believed it.
#
# p6 asks for the AVERAGE salary of the classes in group F. The matcher saw the
# column `groupe` named and the value `F` spoken, surfaced every group-F row,
# and the heading told the model they matched the question. They did not — they
# are per-class MINIMA. The model stated them as an average and a trap that had
# passed since Phase 4 began failing.
#
# The rows are worth having. The claim about them was not.

from tablerag.storage.repositories import TableSource  # noqa: E402


def _source():
    return TableSource(
        element_id=uuid.uuid4(), doc_id=uuid.uuid4(), filename="bareme.pdf",
        page=1, html="<table><tr><td>x</td></tr></table>", summary=None,
        crop_image_path="c.png", confidence=None, needs_review=False)


def test_ranked_rows_are_still_announced_as_matching_the_question():
    block = AssembleContext._table_block(
        _source(), {}, ["groupe: F | classe: 11 | smh: 34 900"], ranked=True)
    assert "matching the question" in block.content


def test_read_rows_are_never_announced_as_matching_the_question():
    block = AssembleContext._table_block(
        _source(), {}, ["groupe: F | classe: 11 | smh: 34 900"], ranked=False)
    assert "matching the question" not in block.content


def test_read_rows_say_how_they_were_chosen_and_that_it_proves_nothing():
    block = AssembleContext._table_block(
        _source(), {}, ["groupe: F | classe: 11 | smh: 34 900"], ranked=False)
    text = block.content.lower()
    # the selection method, stated
    assert "wording" in text
    # and the warning that it is not an answer
    assert "not" in text and "answer" in text


def test_the_rows_themselves_reach_the_prompt_either_way():
    for ranked in (True, False):
        block = AssembleContext._table_block(
            _source(), {}, ["groupe: F | classe: 11 | smh: 34 900"],
            ranked=ranked)
        assert "smh: 34 900" in block.content


def test_a_table_with_no_rows_carries_no_heading_at_all():
    block = AssembleContext._table_block(_source(), {}, [], ranked=False)
    assert "wording" not in block.content.lower()
    assert "matching the question" not in block.content


# --- an enhancement must not be able to kill the answer ---------------------
#
# Reading a table's rows is auxiliary: without it the grid is still in context
# and the model still answers. So a failure here must cost the feature, never
# the reply. group_overlapping sets the precedent two steps away, in the same
# file, with the reason written out: "an answer must survive this".
#
# Shipped without it, which was wrong on its own terms — an outage on the box
# came from Ollama, not from here, but the next one need not be so kind.

class _AngrySession:
    def scalars(self, *_args, **_kwargs):
        raise RuntimeError("connection reset while reading records")


def test_a_failed_row_lookup_costs_the_rows_not_the_answer():
    got = AssembleContext._named_rows(
        _AngrySession(), [uuid.uuid4()], "la classe d'emploi 10")
    assert got == {}


def test_nothing_is_looked_up_when_there_is_no_question():
    # a blank question cannot name a value, so the query is pointless work
    assert AssembleContext._named_rows(_AngrySession(), [uuid.uuid4()], "") == {}


def test_nothing_is_looked_up_when_every_table_already_ranked_rows():
    assert AssembleContext._named_rows(_AngrySession(), [], "la classe 10") == {}
