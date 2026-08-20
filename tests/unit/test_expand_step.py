import contextlib
import uuid

import pytest

from tablerag.query.neighbours import NeighbourCandidate
from tablerag.query.pipeline import QueryContext
from tablerag.query.steps.expand import ExpandNeighbours
from tablerag.storage.qdrant import SearchHit

DOC = uuid.uuid4()


class Boom:
    def __call__(self, *args, **kwargs):
        raise RuntimeError("database is down")


def _hit(element_id: uuid.UUID, score: float = 0.9) -> SearchHit:
    return SearchHit(id=element_id, score=score,
                     payload={"element_id": str(element_id),
                              "doc_id": str(DOC),
                              "_collection": "chunks"})


def _candidate(element_id: uuid.UUID, page: int, y: float,
               type_: str = "text") -> NeighbourCandidate:
    return NeighbourCandidate(element_id=element_id, doc_id=DOC, page=page,
                              y=y, x=0.0, type=type_)


def _stub_database(monkeypatch, candidates):
    """Answer get_page_elements with `candidates` and neutralise the session."""
    monkeypatch.setattr("tablerag.query.steps.expand.get_page_elements",
                        lambda _s, _doc_ids: candidates)
    monkeypatch.setattr("tablerag.query.steps.expand.session_scope",
                        lambda: contextlib.nullcontext(None))


@pytest.mark.asyncio
async def test_expansion_failure_never_fails_the_query(monkeypatch):
    monkeypatch.setattr("tablerag.query.steps.expand.get_page_elements", Boom())
    monkeypatch.setattr("tablerag.query.steps.expand.session_scope",
                        lambda: contextlib.nullcontext(None))
    winner = uuid.uuid4()
    ctx = QueryContext(kb_id=uuid.uuid4(), question="combien ?")
    ctx.hits = [_hit(winner)]
    out = await ExpandNeighbours(enabled=True).run(ctx)
    assert out.hits == ctx.hits  # the ranked hits survive untouched
    assert len(out.hits) == 1


@pytest.mark.asyncio
async def test_disabled_step_is_a_passthrough():
    ctx = QueryContext(kb_id=uuid.uuid4(), question="combien ?")
    ctx.hits = []
    assert await ExpandNeighbours(enabled=False).run(ctx) is ctx


@pytest.mark.asyncio
async def test_expanded_hits_are_appended_after_every_ranked_hit(monkeypatch):
    # position in ctx.hits IS the rank AssembleContext sorts by, and the budget
    # in Task 1 sacrifices from the tail. An expansion inserted anywhere but the
    # end would outrank a real retrieved source and be kept in preference to it.
    winner, before, after = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _stub_database(monkeypatch, [_candidate(before, 1, 100),
                                 _candidate(winner, 1, 200),
                                 _candidate(after, 1, 300)])
    ctx = QueryContext(kb_id=uuid.uuid4(), question="combien ?")
    ctx.hits = [_hit(winner)]
    out = await ExpandNeighbours(enabled=True).run(ctx)

    assert out.hits[0].payload["element_id"] == str(winner)
    assert not out.hits[0].payload.get("_expanded")
    assert {h.payload["element_id"] for h in out.hits[1:]} == {str(before),
                                                               str(after)}
    assert all(h.payload["_expanded"] for h in out.hits[1:])


@pytest.mark.asyncio
async def test_an_expansion_carries_the_element_type_assemble_routes_on(
        monkeypatch):
    # without element_type every expansion is hydrated as a table; a text or
    # figure neighbour has no parent table and would vanish with no error
    winner, figure = uuid.uuid4(), uuid.uuid4()
    _stub_database(monkeypatch, [_candidate(winner, 2, 100),
                                 _candidate(figure, 2, 400, "figure")])
    ctx = QueryContext(kb_id=uuid.uuid4(), question="combien ?")
    ctx.hits = [_hit(winner)]
    out = await ExpandNeighbours(enabled=True).run(ctx)

    [expansion] = out.hits[1:]
    assert expansion.payload["element_id"] == str(figure)
    assert expansion.payload["element_type"] == "figure"


@pytest.mark.asyncio
async def test_a_hit_already_retrieved_is_never_added_a_second_time(monkeypatch):
    first, second = uuid.uuid4(), uuid.uuid4()
    _stub_database(monkeypatch, [_candidate(first, 1, 100),
                                 _candidate(second, 1, 200)])
    ctx = QueryContext(kb_id=uuid.uuid4(), question="combien ?")
    ctx.hits = [_hit(first), _hit(second)]
    out = await ExpandNeighbours(enabled=True).run(ctx)
    assert len(out.hits) == 2  # both were already winners; nothing to add


@pytest.mark.asyncio
async def test_no_hits_means_no_database_call_at_all(monkeypatch):
    monkeypatch.setattr("tablerag.query.steps.expand.get_page_elements", Boom())
    ctx = QueryContext(kb_id=uuid.uuid4(), question="combien ?")
    ctx.hits = []
    out = await ExpandNeighbours(enabled=True).run(ctx)
    assert out.hits == []


def _expanded_hit(element_id: uuid.UUID, element_type: str) -> SearchHit:
    return SearchHit(id=element_id, score=0.0,
                     payload={"element_id": str(element_id),
                              "doc_id": str(DOC),
                              "element_type": element_type,
                              "_collection": "expanded", "_expanded": True})


async def _assemble_with(monkeypatch, hits, expanded_chunk_element=None):
    """Drive AssembleContext over `hits` with the database faked out."""
    from tablerag.storage.repositories import ChunkContext

    from tablerag.query.steps.assemble import AssembleContext

    def fake_fetch(chunk_ids, table_ids, matched, expanded_elements=None,
                   question=""):
        def _ctx(element_id):
            return ChunkContext(chunk_id=uuid.uuid4(), text=f"text of {element_id}",
                                element_id=element_id, page=1,
                                crop_image_path="k", confidence=None,
                                needs_review=False, doc_id=DOC,
                                filename="notice.pdf")

        return ([], [], {},
                [_ctx(e) for e in (expanded_elements or [])
                 if expanded_chunk_element is None or e == expanded_chunk_element],
                {})

    monkeypatch.setattr(AssembleContext, "_fetch", staticmethod(fake_fetch))
    ctx = QueryContext(kb_id=uuid.uuid4(), question="q")
    ctx.hits = hits
    return await AssembleContext().run(ctx)


@pytest.mark.asyncio
async def test_an_expanded_text_element_becomes_a_source_instead_of_vanishing(
        monkeypatch):
    # every non-chunk hit used to go down the table path. A text neighbour has
    # no parent table, so it was looked up as one, found nothing, and dropped
    # out with no error - the feature returning only the tables it pulled.
    neighbour = uuid.uuid4()
    out = await _assemble_with(monkeypatch, [_expanded_hit(neighbour, "text")])
    assert [b.element_id for b in out.sources] == [neighbour]
    assert out.sources[0].kind == "text"


@pytest.mark.asyncio
async def test_an_expanded_source_is_marked_all_the_way_onto_the_citation(
        monkeypatch):
    # the flag exists so the reader can tell what search found from what we
    # brought along. Set on the block but not copied to the Citation, the
    # frontend tag never appears and the feature is silently dead.
    neighbour = uuid.uuid4()
    out = await _assemble_with(monkeypatch, [_expanded_hit(neighbour, "text")])
    assert out.sources[0].expanded is True
    assert out.citations[0].expanded is True
