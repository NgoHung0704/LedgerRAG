"""ModelProvider abstraction (SPEC Phase 1 §2).

One interface, four roles (parser/embedder/chat/reranker). The platform never
talks to a model server except through this interface, so swapping models,
providers or hardware is a config change (constraint C3).
"""

from __future__ import annotations

from typing import AsyncIterator, Literal, Protocol

from pydantic import BaseModel, Field


class SparseVector(BaseModel):
    indices: list[int]
    values: list[float]


class Vector(BaseModel):
    """Dense always; sparse filled by embedders that support it (Phase 4 hybrid)."""

    dense: list[float]
    sparse: SparseVector | None = None


class Msg(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
    images: list[str] = Field(default_factory=list)  # base64-encoded images


class TableCtx(BaseModel):
    """Context handed to the parser role for one table crop."""

    locale_hint: str = "unknown"
    doc_language: str | None = None
    page: int | None = None
    # Phase 3 double-read: variant > 0 shifts seed/temperature so the second
    # read is an independent opinion, not a cache replay
    read_variant: int = 0
    # text-layer grid extracted by find_tables, rendered as a hint: reliable
    # cell VALUES so the VLM only has to infer the merge STRUCTURE from the
    # image (splits the hard problem — see table_parsing.build_user_prompt)
    grid_hint: str | None = None


class RecordParse(BaseModel):
    """One data cell group: dimensions/metrics split (principle #2),
    raw strings always preserved."""

    dimensions: dict
    metrics: dict
    raw_values: dict


class TableParse(BaseModel):
    html: str
    records: list[RecordParse]
    raw_response: str = ""
    # honest failure (SPEC §0.3): contract violation after retry — records are
    # empty, whatever HTML was salvaged is kept, caller flags needs_review
    error: str | None = None


class ModelProvider(Protocol):
    """All methods are async; `chat` is an async generator (use `async for`)."""

    async def parse_table(self, image: bytes, prompt_ctx: TableCtx) -> TableParse: ...

    async def embed(self, texts: list[str]) -> list[Vector]: ...

    def chat(self, messages: list[Msg], stream: bool = True,
             temperature: float | None = None,
             options: dict | None = None) -> AsyncIterator[str]: ...

    async def rerank(self, query: str, docs: list[str]) -> list[float]: ...

    async def health(self) -> tuple[bool, str]: ...
