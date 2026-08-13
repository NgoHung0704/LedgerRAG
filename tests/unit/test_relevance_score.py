"""The number under a citation must be how well it answered, not how it was found.

Rerank reorders the hits and never writes the cross-encoder's score onto them,
so Citation.score carried the hybrid-fusion score from retrieval. Dimming a
source list by that number would dim by the wrong thing: RRF says "several
searches agreed this was worth looking at", the cross-encoder says "this passage
answers the question", and only the second is what a reader is being shown.
"""

import uuid

import pytest

from tablerag.query.steps.rerank import carry_rerank_score, relevance_of
from tablerag.storage.qdrant import SearchHit


def _hit(score: float) -> SearchHit:
    return SearchHit(id=uuid.uuid4(), score=score, payload={"_collection": "chunks"})


def test_the_cross_encoder_score_is_written_onto_the_hit():
    hit = _hit(0.031)          # an RRF score
    carry_rerank_score(hit, 0.87)
    assert relevance_of(hit) == pytest.approx(0.87)


def test_the_retrieval_score_is_kept_not_overwritten():
    # it is still the reason the candidate was in the pool at all
    hit = _hit(0.031)
    carry_rerank_score(hit, 0.87)
    assert hit.score == pytest.approx(0.031)


def test_a_hit_the_reranker_never_saw_falls_back_to_its_own_score():
    # the reranker is pluggable and may be disabled; the number must still mean
    # something rather than becoming zero for every source
    assert relevance_of(_hit(0.031)) == pytest.approx(0.031)
