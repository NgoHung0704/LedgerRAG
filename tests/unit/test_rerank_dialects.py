"""The bundled reranker speaks TEI; the one Phase 4 was measured on spoke vLLM.

Both are "the /rerank endpoint". They disagree on the request field name and on
whether the response is wrapped, and getting it wrong is silent: the Rerank step
catches everything and falls back to document diversification, so the pipeline
produces exactly the numbers it produces with no reranker at all.
"""

import json

import httpx
import pytest

from tablerag.core.config import EndpointConfig
from tablerag.models.openai_compat import OpenAICompatProvider

DOCS = ["la volatilité annualisée sur 3 ans est 2,63",
        "le taux de sélection SR est 44,20"]


def _provider(handler) -> OpenAICompatProvider:
    provider = OpenAICompatProvider(EndpointConfig(
        provider="openai_compat", base_url="http://reranker:80",
        model_name="BAAI/bge-reranker-v2-m3"))
    provider._transport = httpx.MockTransport(handler)
    return provider


@pytest.mark.asyncio
async def test_tei_bare_list_response_and_texts_field():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.update(body)
        if "texts" not in body:            # TEI rejects the vLLM field name
            return httpx.Response(422, json={"error": "missing field `texts`"})
        return httpx.Response(200, json=[{"index": 1, "score": 0.9},
                                         {"index": 0, "score": 0.1}])

    scores = await _provider(handler).rerank("volatilité 3 ans", DOCS)
    assert scores == [0.1, 0.9]
    assert "texts" in seen


@pytest.mark.asyncio
async def test_vllm_wrapped_response_and_documents_field():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "documents" in body
        return httpx.Response(200, json={"results": [
            {"index": 0, "relevance_score": 0.7},
            {"index": 1, "relevance_score": 0.2}]})

    scores = await _provider(handler).rerank("volatilité 3 ans", DOCS)
    assert scores == [0.7, 0.2]
