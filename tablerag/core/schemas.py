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


class KBOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
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
