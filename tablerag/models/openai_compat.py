"""OpenAI-compatible provider (vLLM, llama.cpp server, TEI, or hosted APIs).

Only used when the deploying engineer explicitly enables it (constraint C1:
local-only deployments never point this at an external host).
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from tablerag.core.config import EndpointConfig
from tablerag.models.base import Msg, TableCtx, TableParse, Vector

_TIMEOUT = httpx.Timeout(600.0, connect=10.0)
# TEI accepts 32 texts per request and 2 MB of payload; the candidate pool is
# retrieve_candidates=50. One request for the pool returns 413, the Rerank step
# swallows it, and the pipeline silently falls back to document diversification.
_RERANK_BATCH = 16
# a cross-encoder judges whether a passage is ABOUT the question; it does not
# hunt for a cell. The head of a table - summary, headers, first rows - carries
# that, and sending 200 kB of grid costs the payload limit for nothing.
_RERANK_DOC_CHARS = 4000


class OpenAICompatProvider:
    def __init__(self, cfg: EndpointConfig):
        self.base_url = cfg.base_url.rstrip("/")
        self.model = cfg.model_name
        self.headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
        # test seam: an httpx transport to answer /rerank without a server
        self._transport = None

    async def parse_table(self, image: bytes, prompt_ctx: TableCtx) -> TableParse:
        from tablerag.models.table_parsing import run_table_parse

        return await run_table_parse(self.chat, image, prompt_ctx)

    async def embed(self, texts: list[str]) -> list[Vector]:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self.headers) as client:
            r = await client.post(f"{self.base_url}/v1/embeddings",
                                  json={"model": self.model, "input": texts})
            r.raise_for_status()
            data = r.json()["data"]
        data.sort(key=lambda d: d["index"])
        return [Vector(dense=d["embedding"]) for d in data]

    async def chat(self, messages: list[Msg], stream: bool = True,
                   temperature: float | None = None,
                   options: dict | None = None) -> AsyncIterator[str]:
        def to_openai(m: Msg) -> dict:
            if not m.images:
                return {"role": m.role, "content": m.content}
            content = [{"type": "text", "text": m.content}] + [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{img}"}}
                for img in m.images
            ]
            return {"role": m.role, "content": content}

        opts = options or {}
        payload = {"model": self.model, "stream": True,
                   "messages": [to_openai(m) for m in messages]}
        temp = opts.get("temperature", temperature)
        if temp is not None:
            payload["temperature"] = temp
        if "seed" in opts:
            payload["seed"] = opts["seed"]
        if "num_predict" in opts:  # Ollama name -> OpenAI name; num_ctx is server-side
            payload["max_tokens"] = opts["num_predict"]
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self.headers) as client:
            async with client.stream("POST", f"{self.base_url}/v1/chat/completions",
                                     json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    chunk = json.loads(body)
                    delta = chunk["choices"][0].get("delta", {})
                    if content := delta.get("content"):
                        yield content

    async def rerank(self, query: str, docs: list[str]) -> list[float]:
        """Score `docs` against `query`, in either /rerank dialect.

        "The OpenAI-compatible /rerank endpoint" is two incompatible things.
        vLLM and Jina take `documents` and answer {"results": [...]}; TEI - the
        reranker this repo's own compose file ships - takes `texts` and answers
        a BARE LIST. Sending the wrong field is a 4xx and reading the wrong
        shape raises, and the Rerank step catches everything and degrades to
        document diversification. So the whole feature came out looking
        configured and behaving exactly as if it were disabled.

        Batched and truncated for the same reason: measured on the box, the
        full 50-candidate pool returned 413 Payload Too Large, and that also
        degraded silently."""
        scores = [0.0] * len(docs)
        clipped = [d[:_RERANK_DOC_CHARS] for d in docs]
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self.headers,
                                     transport=self._transport) as client:
            url = f"{self.base_url}/rerank"
            for start in range(0, len(clipped), _RERANK_BATCH):
                batch = clipped[start:start + _RERANK_BATCH]
                r = await client.post(url, json={"model": self.model,
                                                 "query": query,
                                                 "documents": batch})
                if r.status_code in (400, 422):  # wrong field name -> TEI's
                    r = await client.post(url, json={"query": query,
                                                     "texts": batch})
                r.raise_for_status()
                payload = r.json()
                results = (payload if isinstance(payload, list)
                           else payload["results"])
                for item in results:
                    scores[start + item["index"]] = item.get(
                        "relevance_score", item.get("score", 0.0))
        return scores

    async def health(self) -> tuple[bool, str]:
        """Alive on either kind of server behind this provider.

        base_url may already end in /v1 (a rerank vLLM is commonly configured
        as http://host:8007/v1), so normalise first or the probe becomes
        /v1/v1/models and reports a false "unhealthy".

        Then try both doors. TEI - the reranker this repo ships - has no
        /v1/models at all, because it is not a chat server; probing only that
        path paints a working reranker red, and a red light nobody trusts is
        how a broken endpoint hides in plain sight. Its /health is the door it
        does answer."""
        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        last = ""
        for path in ("/v1/models", "/health"):
            try:
                async with httpx.AsyncClient(timeout=5.0,
                                             headers=self.headers,
                                             transport=self._transport) as client:
                    r = await client.get(f"{root}{path}")
                    r.raise_for_status()
                    return True, "ok"
            except (httpx.HTTPError, OSError) as e:
                last = str(e)
        return False, last
