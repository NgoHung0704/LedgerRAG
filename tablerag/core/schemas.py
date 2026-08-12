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
    # who a reader should ask when an answer is flagged as needing a check.
    # Lives in KnowledgeBase.config JSONB, not a column: create_all adds
    # tables, never columns, and this project carries no migrations.
    escalation_contact: str | None = None


class KBDocStatus(BaseModel):
    """At-a-glance ingestion state of a KB's documents, for the KB list card:
    is it done, still processing, or does it hold failed files? Populated only
    by the list endpoint (None elsewhere — single-KB reads don't need it)."""
    total: int = 0
    processing: int = 0  # queued + parsing + indexing
    done: int = 0
    failed: int = 0


class KBOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    config: dict = {}
    created_at: datetime
    doc_status: KBDocStatus | None = None


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


class AssistantCreate(BaseModel):
    """A chat app: its own knowledge bases, its own system prompt."""
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    instructions: str = ""       # appended to the safety core, never replaces it
    kb_ids: list[uuid.UUID] = []  # the context it searches
    opening_message: str = ""    # shown in an empty conversation
    verify: bool | None = None   # override number verification for this app


class AssistantUpdate(BaseModel):
    """Partial update — only what is sent changes. `kb_ids`, when sent, REPLACES
    the attached set."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    instructions: str | None = None
    kb_ids: list[uuid.UUID] | None = None
    opening_message: str | None = None
    verify: bool | None = None


class AssistantOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    instructions: str
    kb_ids: list[uuid.UUID]
    kb_names: list[str]
    opening_message: str = ""
    verify: bool | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    session_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class AssistantChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: uuid.UUID | None = None
    verify: bool | None = None


class ChatInstructions(BaseModel):
    """Global chat persona (admin). `identity` is who the assistant says it is
    (it answers "who are you?" without searching); `text` is extra guidance
    appended to the system prompt. Both additive — the hardcoded safety rules
    always take precedence."""
    identity: str = ""
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
    # this source's text is a MODEL'S DESCRIPTION of a picture, not text read
    # off the page — `kind` stays "text" because that is the collection it was
    # retrieved from, and the ranking is keyed by it
    from_figure: bool = False
    # pulled in because it neighbours a retrieved source, not because search
    # found it - a reader must be able to tell the two apart
    expanded: bool = False


class Caution(BaseModel):
    """Why this answer deserves a second look, and who to ask.

    `reasons` are stable machine keys, not prose: the UI renders them in the
    reader's language and an API consumer can act on them."""

    reasons: list[str] = []
    contact: str | None = None


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


class AssistTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ElementAssistRequest(BaseModel):
    """Ask the chat model to help edit the content open in the editor. The
    content travels with the request because it is UNSAVED."""
    instruction: str = Field(min_length=1, max_length=2000)
    format: Literal["html", "text", "records", "summary"] = "text"
    content: str = ""
    history: list[AssistTurn] = []


class DeriveFromHtmlRequest(BaseModel):
    """Rebuild a table's records and summary from HTML being edited (unsaved)."""
    html: str = Field(min_length=1)


class BulkDeleteRequest(BaseModel):
    doc_ids: list[uuid.UUID] = Field(min_length=1)


class BoilerplateCandidate(BaseModel):
    """A text element that looks like a running header/footer/page number —
    a candidate to exclude from retrieval, pending human review."""
    element_id: uuid.UUID
    page: int
    reason: str
    text: str


class BoilerplateExcludeRequest(BaseModel):
    element_ids: list[uuid.UUID] = Field(min_length=1)


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
    # which layer decided this role: "database" | "environment" | "default".
    # A database row silently beating an edited .env cost a day of measurement.
    source: str = "default"
    # what the environment says, even when something else won — so an operator
    # can see their .env being masked instead of guessing
    env: dict[str, str] = {}
    # a role that IS configured and whose last call failed. Distinct from
    # ok=False: that is a health probe, this is the pipeline actually degrading.
    last_error: str | None = None


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
