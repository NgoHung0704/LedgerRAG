"""A cross-encoder trained on prose will not rank a table row above a paragraph.

Measured on the box: the candidate pool was a third chunks, a third records, a
third table summaries - and the reranker kept eight chunks and nothing else, on
ten queries out of ten. Not a preference, a sweep. bge-reranker-v2-m3 judges
whether a PASSAGE answers a question, and "Portefeuille | 1 mois: -2,58 | 2021:
9,42" is not a passage, however exactly it holds the answer.

So the table sub-pipeline - the reason this product exists - was absent from the
context on sixteen of seventeen questions, and the assistant answered table
questions by reading page prose.
"""

import uuid
from collections import Counter

from tablerag.query.steps.rerank import reserve_structured_slots
from tablerag.storage.qdrant import (
    COLLECTION_CHUNKS,
    COLLECTION_RECORDS,
    COLLECTION_TABLE_SUMMARIES,
    SearchHit,
)


def _hit(collection: str) -> SearchHit:
    return SearchHit(id=uuid.uuid4(), score=0.0,
                     payload={"_collection": collection})


def _mix(hits) -> Counter:
    return Counter(h.payload["_collection"] for h in hits)


def test_a_clean_sweep_by_one_collection_is_broken_up():
    # exactly what the box produced: prose wins every slot
    ranked = [_hit(COLLECTION_CHUNKS) for _ in range(20)] + \
             [_hit(COLLECTION_RECORDS) for _ in range(10)]
    kept = reserve_structured_slots(ranked, top_k=8, reserve=3)
    assert len(kept) == 8
    assert _mix(kept)[COLLECTION_RECORDS] == 3
    assert _mix(kept)[COLLECTION_CHUNKS] == 5


def test_the_best_of_each_kind_is_what_survives():
    best_record = _hit(COLLECTION_RECORDS)
    ranked = [_hit(COLLECTION_CHUNKS) for _ in range(8)] + [best_record] + \
             [_hit(COLLECTION_RECORDS) for _ in range(5)]
    kept = reserve_structured_slots(ranked, top_k=8, reserve=1)
    assert best_record in kept, "the highest-ranked record must be the one kept"


def test_the_weakest_prose_slot_is_the_one_given_up():
    # giving up the TOP chunk to make room trades the best passage for a table
    # row, which is a different and much worse bargain
    chunks = [_hit(COLLECTION_CHUNKS) for _ in range(10)]
    record = _hit(COLLECTION_RECORDS)
    kept = reserve_structured_slots(chunks + [record], top_k=8, reserve=1)
    assert chunks[0] in kept, "the best passage must not be the one dropped"
    assert chunks[7] not in kept, "the weakest kept chunk is what makes room"
    assert record in kept


def test_rank_order_is_preserved():
    # AssembleContext reads position as rank; reordering here would silently
    # undo the reranker's decision, the bug diversify_by_document was once
    # caught causing.
    #
    # The records sit in the MIDDLE on purpose. With them at the end, a function
    # that simply appends what it rescues comes out in rank order by accident,
    # and this test cannot tell the two apart.
    #
    # Honest limit, measured: appending rescued hits is EQUIVALENT to
    # filtering, because a rescued hit always ranked below the kept ones.
    # What this does catch is the realistic mistake - sorting the output so
    # structured hits come first, which would hand the model a table where
    # the reranker put a paragraph.
    ranked = ([_hit(COLLECTION_CHUNKS) for _ in range(4)]
              + [_hit(COLLECTION_RECORDS) for _ in range(2)]
              + [_hit(COLLECTION_CHUNKS) for _ in range(8)])
    kept = reserve_structured_slots(ranked, top_k=8, reserve=2)
    positions = [ranked.index(h) for h in kept]
    assert positions == sorted(positions), "returned out of rank order"


def test_a_pool_with_no_tables_is_left_exactly_as_it_was():
    ranked = [_hit(COLLECTION_CHUNKS) for _ in range(20)]
    assert reserve_structured_slots(ranked, top_k=8, reserve=3) == ranked[:8]


def test_reserving_more_than_exist_takes_what_there_is():
    ranked = [_hit(COLLECTION_CHUNKS) for _ in range(20)] + \
             [_hit(COLLECTION_TABLE_SUMMARIES)]
    kept = reserve_structured_slots(ranked, top_k=8, reserve=3)
    assert len(kept) == 8
    assert _mix(kept)[COLLECTION_TABLE_SUMMARIES] == 1


def test_structured_hits_that_already_won_are_not_double_counted():
    ranked = [_hit(COLLECTION_RECORDS) for _ in range(4)] + \
             [_hit(COLLECTION_CHUNKS) for _ in range(10)]
    kept = reserve_structured_slots(ranked, top_k=8, reserve=3)
    assert _mix(kept)[COLLECTION_RECORDS] == 4, "already ahead: nothing to force"
    assert len(kept) == 8
