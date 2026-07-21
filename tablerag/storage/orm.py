"""ORM mapping of the data model (SPEC §3.2).

JSONB on Postgres with a plain-JSON fallback so unit tests can run on SQLite.
`element.meta` is not in the §3.2 listing but is referenced by Phase 3
(`element.meta.confidence_detail`), so it exists from day one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")  # router input (Phase 5)
    config: Mapped[dict] = mapped_column(JSONVariant, default=dict)  # per-KB overrides
    created_at: Mapped[datetime] = _created_at()

    documents: Mapped[list["Document"]] = relationship(
        back_populates="kb", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','parsing','indexing','done','failed')",
            name="document_status_check"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    kb_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_base.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str] = mapped_column(Text)  # object-store key of the original PDF
    created_at: Mapped[datetime] = _created_at()

    kb: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    elements: Mapped[list["Element"]] = relationship(
        back_populates="document", cascade="all, delete-orphan")


class Element(Base):
    __tablename__ = "element"
    __table_args__ = (
        CheckConstraint("type IN ('text','table','figure')", name="element_type_check"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    doc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True)
    page: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[list] = mapped_column(JSONVariant)  # [x0, y0, x1, y1]
    type: Mapped[str] = mapped_column(Text)
    # principle #3: every element traces back to a stored crop image — no exceptions
    crop_image_path: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = _created_at()

    document: Mapped[Document] = relationship(back_populates="elements")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="element", cascade="all, delete-orphan")
    table: Mapped["TableElement | None"] = relationship(
        back_populates="element", cascade="all, delete-orphan", uselist=False)


class TableElement(Base):
    __tablename__ = "table_element"

    element_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("element.id", ondelete="CASCADE"), primary_key=True)
    html: Mapped[str | None] = mapped_column(Text)      # representation 1: display
    summary: Mapped[str | None] = mapped_column(Text)   # representation 3: routing
    n_rows: Mapped[int | None] = mapped_column(Integer)
    n_cols: Mapped[int | None] = mapped_column(Integer)
    parse_strategy: Mapped[str | None] = mapped_column(Text)  # 'simple_parser' | 'vlm'

    element: Mapped[Element] = relationship(back_populates="table")
    records: Mapped[list["Record"]] = relationship(
        back_populates="table_element", cascade="all, delete-orphan")


class Record(Base):
    """Representation 2: dimensions/metrics split for exact numeric lookup."""

    __tablename__ = "record"

    id: Mapped[uuid.UUID] = _uuid_pk()
    table_element_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("table_element.element_id", ondelete="CASCADE"), index=True)
    dimensions: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    raw_values: Mapped[dict] = mapped_column(JSONVariant, nullable=False)  # never overwritten
    text_repr: Mapped[str] = mapped_column(Text, nullable=False)  # embedded string

    table_element: Mapped[TableElement] = relationship(back_populates="records")


class Chunk(Base):
    __tablename__ = "chunk"

    id: Mapped[uuid.UUID] = _uuid_pk()
    element_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("element.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)

    element: Mapped[Element] = relationship(back_populates="chunks")


class AppSetting(Base):
    """Runtime configuration overrides (e.g. model-role endpoints edited from
    the admin UI). Env config is the base; these win when present."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatSession(Base):
    __tablename__ = "chat_session"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kb_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_base.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = _created_at()


class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_session.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)
    verification: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class AuditEvent(Base):
    """GDPR accountability (SPEC Phase 5): who did what, when. Its own table so
    create_all adds it with no migration. actor is the proxy identity (or
    'local' in disabled mode)."""

    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = _uuid_pk()
    actor: Mapped[str] = mapped_column(Text, index=True)
    action: Mapped[str] = mapped_column(Text, index=True)  # upload | query | model_config
    kb_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    doc_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class MessageFeedback(Base):
    """Phase 5 👍/👎 on an answer. Its own table (not a chat_message column) so
    `create_all` picks it up on an existing DB without a migration. One row per
    message (unique), value +1 / -1; feeds the eval-as-asset dogfood loop."""

    __tablename__ = "message_feedback"

    id: Mapped[uuid.UUID] = _uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_message.id", ondelete="CASCADE"),
        unique=True, index=True)
    value: Mapped[int] = mapped_column(Integer)  # +1 up, -1 down
    created_at: Mapped[datetime] = _created_at()
