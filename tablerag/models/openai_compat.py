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
        """Matches the TEI / Jina / vLLM `/rerank` request shape."""
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self.headers) as client:
            r = await client.post(
                f"{self.base_url}/rerank",
                json={"model": self.model, "query": query, "documents": docs})
            r.raise_for_status()
            results = r.json()["results"]
        scores = [0.0] * len(docs)
        for item in results:
            scores[item["index"]] = item.get("relevance_score", item.get("score", 0.0))
        return scores

    async def health(self) -> tuple[bool, str]:
        # base_url may or may not already end in /v1 (a rerank vLLM is commonly
        # configured as http://host:8007/v1). Normalize so the check hits
        # /v1/models either way instead of /v1/v1/models -> false "unhealthy".
        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        try:
            async with httpx.AsyncClient(timeout=5.0, headers=self.headers) as client:
                r = await client.get(f"{root}/v1/models")
                r.raise_for_status()
                return True, "ok"
        except (httpx.HTTPError, OSError) as e:
            return False, str(e)
