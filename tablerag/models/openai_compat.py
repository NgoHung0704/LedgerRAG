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
        vLLM and Jina take `documents` and answer `{"results": [...]}`; TEI —
        the reranker this repo's own compose file ships — takes `texts` and
        answers a BARE LIST. Sending the wrong field is a 422 and reading the
        wrong shape raises, and the Rerank step catches everything and falls
        back to document diversification. So the whole feature came out looking
        configured and behaving exactly as if it were disabled: measured on the
        box, the scores were identical to the no-reranker run, to the question.

        Try the vLLM field first (that is what Phase 4 was measured against),
        fall back to TEI's on a 4xx, and accept either response shape."""
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self.headers,
                                     transport=self._transport) as client:
            url = f"{self.base_url}/rerank"
            r = await client.post(url, json={"model": self.model,
                                             "query": query,
                                             "documents": docs})
            if 400 <= r.status_code < 500:
                r = await client.post(url, json={"query": query, "texts": docs})
            r.raise_for_status()
            payload = r.json()
        results = payload if isinstance(payload, list) else payload["results"]
        scores = [0.0] * len(docs)
        for item in results:
            scores[item["index"]] = item.get("relevance_score",
                                             item.get("score", 0.0))
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
