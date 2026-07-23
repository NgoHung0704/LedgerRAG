"""API-facing pydantic schemas (DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DocumentStatus = Literal["queued", "parsing", "indexing", "done", "failed"]


class KBCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""  # router input from Phase 5; stored from day one
    # declared number locale of the documents (SPEC Phase 2 §5: declared beats
    # guessed); None = unknown, the pipeline stays conservative
    locale: str | None = None
    # answer-number verification (Phase 4); default ON — this is a numbers tool
    verify: bool = True
    # extra guidance appended to the chat system prompt for this KB (tone,
    # focus, formatting). Additive only — it never overrides the safety rules.
    instructions: str = ""


class KBUpdate(BaseModel):
    """Partial update of a KB's settings. Every field optional: only what is
    sent is changed, so a KB created before a setting existed can adopt it
    without being recreated (run 2 could not enable verification on an
    existing KB — its stored config pinned it off)."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    locale: str | None = None
    verify: bool | None = None
    instructions: str | None = None


class KBOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    config: dict = {}
    created_at: datetime


class DocumentOut(BaseModel):
    id: uuid.UUID
    kb_id: uuid.UUID
    filename: str
    status: DocumentStatus
    error: str | None = None
    page_count: int | None = None
    created_at: datetime


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: uuid.UUID | None = None
    verify: bool | None = None  # per-request override of number verification


class MultiChatRequest(BaseModel):
    """Phase 5 multi-KB chat. kb_ids pins the search (manual override); when
    omitted the LLMRouter picks from all KBs by their descriptions."""
    question: str = Field(min_length=1)
    kb_ids: list[uuid.UUID] | None = None
    session_id: uuid.UUID | None = None
    verify: bool | None = None


class FeedbackRequest(BaseModel):
    value: int = Field(ge=-1, le=1)  # +1 👍, -1 👎, 0 clears


class ChatInstructions(BaseModel):
    """Global extra guidance appended to every chat system prompt (admin).
    Additive only — the hardcoded safety rules always take precedence."""
    text: str = ""


class Citation(BaseModel):
    """Every element traces back to its origin (principle #3)."""

    index: int  # [n] marker used in the answer text
    kind: Literal["text", "table"] = "text"
    doc_id: uuid.UUID
    filename: str
    page: int
    element_id: uuid.UUID
    chunk_id: uuid.UUID | None = None
    snippet: str
    score: float
    crop_image_path: str | None = None
    confidence: float | None = None
    needs_review: bool = False


class RecordEdit(BaseModel):
    dimensions: dict = {}
    metrics: dict = {}
    raw_values: dict = {}


class ElementEdit(BaseModel):
    """Manual correction of a parsed element (SPEC §0.3 human-in-the-loop).
    Any provided field is applied; the element is re-indexed so answers use the
    corrected data. Fields not sent are left unchanged."""

    text: str | None = None          # text elements: re-chunked + re-embedded
    html: str | None = None          # table display / answer context
    summary: str | None = None       # table routing summary (re-embedded)
    records: list[RecordEdit] | None = None  # table records (re-embedded)


class BulkDeleteRequest(BaseModel):
    doc_ids: list[uuid.UUID] = Field(min_length=1)


class RoleHealth(BaseModel):
    role: str
    provider: str
    model: str
    ok: bool
    detail: str = ""


class ModelRoleInfo(BaseModel):
    role: str
    provider: str
    base_url: str
    model_name: str
    overridden: bool  # True when a runtime override (admin UI) is active
    ok: bool
    detail: str = ""


class ModelRoleUpdate(BaseModel):
    provider: Literal["ollama", "openai_compat", "disabled"] | None = None
    base_url: str | None = None
    model_name: str | None = None
    api_key: str | None = None


class OllamaModel(BaseModel):
    name: str
    size_bytes: int | None = None
    parameter_size: str | None = None


class PullRequest(BaseModel):
    name: str = Field(min_length=1)
