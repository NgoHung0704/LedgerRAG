import uuid

from tablerag.query.pipeline import SourceBlock
from tablerag.query.steps.assemble import trim_to_budget


def _block(content: str, expanded: bool = False) -> SourceBlock:
    return SourceBlock(
        kind="text", doc_id=uuid.uuid4(), filename="notice.pdf", page=1,
        element_id=uuid.uuid4(), chunk_id=uuid.uuid4(), content=content,
        snippet=content[:240], score=0.5, crop_image_path="c.png",
        confidence=1.0, expanded=expanded)


def test_under_budget_keeps_everything():
    blocks = [_block("a" * 100), _block("b" * 100)]
    kept, dropped = trim_to_budget(blocks, 1000)
    assert kept == blocks
    assert dropped == []


def test_expansions_are_sacrificed_before_primary_sources():
    primary_a, primary_b = _block("a" * 100), _block("b" * 100)
    extra = _block("c" * 100, expanded=True)
    kept, dropped = trim_to_budget([primary_a, primary_b, extra], 250)
    assert kept == [primary_a, primary_b]
    assert len(dropped) == 1


def test_the_top_ranked_source_is_never_dropped():
    blocks = [_block("a" * 500), _block("b" * 500)]
    kept, dropped = trim_to_budget(blocks, 10)
    assert len(kept) == 1
    assert kept[0] is blocks[0]
    # it does not fit either, so it was truncated rather than dropped
    assert len(kept[0].content) <= 10
    assert dropped


def test_truncation_happens_only_after_dropping_is_exhausted():
    keep, drop = _block("a" * 200), _block("b" * 200)
    kept, _ = trim_to_budget([keep, drop], 200)
    assert len(kept) == 1
    assert kept[0].content == "a" * 200  # untouched: dropping was enough
