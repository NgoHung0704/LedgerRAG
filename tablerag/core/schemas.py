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
