"""Ollama provider (default local serving backend)."""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from tablerag.core.config import EndpointConfig
from tablerag.models.base import Msg, TableCtx, TableParse, Vector

_TIMEOUT = httpx.Timeout(600.0, connect=10.0)


class OllamaProvider:
    def __init__(self, cfg: EndpointConfig):
        self.base_url = cfg.base_url.rstrip("/")
        self.model = cfg.model_name

    async def parse_table(self, image: bytes, prompt_ctx: TableCtx) -> TableParse:
        # The table prompt/validation pipeline is promoted from spike/ in
        # Phase 2 (ingestion/table_vlm.py drives this role).
        raise NotImplementedError("table parsing arrives in Phase 2")

    async def embed(self, texts: list[str]) -> list[Vector]:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(f"{self.base_url}/api/embed",
                                  json={"model": self.model, "input": texts})
            r.raise_for_status()
            data = r.json()
        return [Vector(dense=e) for e in data["embeddings"]]

    async def chat(self, messages: list[Msg], stream: bool = True) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [m.model_dump(exclude_defaults=True) for m in messages],
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat",
                                     json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if content := chunk.get("message", {}).get("content"):
                        yield content
                    if chunk.get("done"):
                        break

    async def rerank(self, query: str, docs: list[str]) -> list[float]:
        raise NotImplementedError(
            "Ollama has no rerank API; configure an openai_compat rerank endpoint "
            "or leave the reranker role disabled")

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/version")
                r.raise_for_status()
                return True, f"ollama {r.json().get('version', '?')}"
        except (httpx.HTTPError, OSError) as e:
            return False, str(e)
