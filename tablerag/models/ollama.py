"""Ollama provider (default local serving backend)."""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from tablerag.core.config import EndpointConfig
from tablerag.models.base import Msg, TableCtx, TableParse, Vector

_TIMEOUT = httpx.Timeout(600.0, connect=10.0)


def model_present(model: str, installed: list[str]) -> bool:
    """Ollama tags carry a ':tag' suffix; a config without one means ':latest'."""
    if not model or model in installed:
        return True
    if ":" not in model:
        return any(name.split(":")[0] == model for name in installed)
    return False


class OllamaProvider:
    def __init__(self, cfg: EndpointConfig):
        self.base_url = cfg.base_url.rstrip("/")
        self.model = cfg.model_name

    async def parse_table(self, image: bytes, prompt_ctx: TableCtx) -> TableParse:
        from tablerag.models.table_parsing import run_table_parse

        return await run_table_parse(self.chat, image, prompt_ctx)

    async def embed(self, texts: list[str]) -> list[Vector]:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(f"{self.base_url}/api/embed",
                                  json={"model": self.model, "input": texts})
            r.raise_for_status()
            data = r.json()
        return [Vector(dense=e) for e in data["embeddings"]]

    async def chat(self, messages: list[Msg], stream: bool = True,
                   temperature: float | None = None,
                   options: dict | None = None) -> AsyncIterator[str]:
        opts = dict(options or {})
        if temperature is not None:
            opts.setdefault("temperature", temperature)
        payload = {
            "model": self.model,
            "messages": [m.model_dump(exclude_defaults=True) for m in messages],
            "stream": True,
        }
        if opts:
            payload["options"] = opts
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
        # verify both reachability AND that the configured model is installed —
        # a reachable Ollama without the model 404s at parse time (honest fail
        # up front beats a false green in the UI)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                tags = await client.get(f"{self.base_url}/api/tags")
                tags.raise_for_status()
                installed = [m.get("name", "") for m in tags.json().get("models", [])]
        except (httpx.HTTPError, OSError) as e:
            return False, f"endpoint unreachable: {e}"
        if not model_present(self.model, installed):
            return False, (f"reachable, but model '{self.model}' is not installed "
                           f"here — pull it or pick an installed model")
        return True, f"model '{self.model}' ready"
