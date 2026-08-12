"""A reranker that works must not show a red light.

TEI serves /health and /rerank; it has no /v1/models, because it is not a chat
server. Probing only /v1/models reports a working reranker as unhealthy - the
same misleading-signal class that cost a day of measurement on the box.
"""

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
async def test_a_tei_server_with_no_v1_models_is_still_healthy():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(404, text="Not Found")
        if request.url.path == "/health":
            return httpx.Response(200, text="")
        return httpx.Response(500)

    ok, detail = await _provider(handler).health()
    assert ok, detail


@pytest.mark.asyncio
async def test_an_openai_style_server_is_still_healthy():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    ok, _ = await _provider(handler).health()
    assert ok


@pytest.mark.asyncio
async def test_a_server_that_is_really_down_is_reported_down():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    ok, detail = await _provider(handler).health()
    assert not ok
    assert detail
