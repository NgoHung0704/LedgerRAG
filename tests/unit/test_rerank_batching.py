"""The candidate pool is 50; TEI accepts 32 per request and 2 MB of payload.

Sending the pool in one request returns 413 Payload Too Large, the Rerank step
catches it, and the pipeline degrades to document diversification - which on a
corpus of near-identical fund factsheets is the worst available ordering. The
failure is invisible in the answer: it just looks like a bad ranking.
"""

import json

import httpx
import pytest

from tablerag.core.config import EndpointConfig
from tablerag.models.openai_compat import OpenAICompatProvider


def _provider(handler) -> OpenAICompatProvider:
    provider = OpenAICompatProvider(EndpointConfig(
        provider="openai_compat", base_url="http://reranker:80",
        model_name="BAAI/bge-reranker-v2-m3"))
    provider._transport = httpx.MockTransport(handler)
    return provider


@pytest.mark.asyncio
async def test_a_pool_of_fifty_is_split_into_accepted_batches():
    sizes, seen = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        docs = body.get("documents") or body.get("texts")
        sizes.append(len(docs))
        seen.extend(docs)
        return httpx.Response(200, json=[{"index": i, "score": float(i)}
                                         for i in range(len(docs))])

    docs = [f"passage {i}" for i in range(50)]
    scores = await _provider(handler).rerank("q", docs)

    assert len(scores) == 50
    assert max(sizes) <= 32, f"a batch of {max(sizes)} would be rejected"
    assert seen == docs, "every candidate must be scored, in order"


@pytest.mark.asyncio
async def test_scores_land_on_the_right_documents_across_batches():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        docs = body.get("documents") or body.get("texts")
        # score = the passage's own number, so misalignment is visible
        return httpx.Response(200, json=[
            {"index": i, "score": float(d.split()[-1])}
            for i, d in enumerate(docs)])

    docs = [f"passage {i}" for i in range(40)]
    scores = await _provider(handler).rerank("q", docs)
    assert scores == [float(i) for i in range(40)]


@pytest.mark.asyncio
async def test_a_whole_table_is_truncated_before_it_is_sent():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.extend(body.get("documents") or body.get("texts"))
        return httpx.Response(200, json=[{"index": 0, "score": 1.0}])

    await _provider(handler).rerank("q", ["x" * 200_000])
    assert len(sent[0]) < 200_000, "a 200 kB table would blow the payload limit"
