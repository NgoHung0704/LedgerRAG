"""Rerank step (Phase 4): reorder the hybrid candidate pool with the
`reranker` model role (e.g. bge-reranker-v2-m3 behind a TEI/openai_compat
endpoint) and keep the best few for context.

The role is disabled by default — then this step just truncates the pool to
`fallback_top_k` (the Phase 1 behavior). When enabled but unreachable, it
degrades to the same truncation instead of failing the question (honest
degradation, never a dead chat)."""

from __future__ import annotations

import asyncio
import logging
import uuid

from tablerag.core.config import get_settings
from tablerag.models.registry import RoleDisabled, effective_config, get_provider
from tablerag.query.pipeline import QueryContext

logger = logging.getLogger(__name__)


class Rerank:
    def __init__(self, top_k: int = 8, fallback_top_k: int = 12):
        self.top_k = top_k
        self.fallback_top_k = fallback_top_k

    async def run(self, ctx: QueryContext) -> QueryContext:
        if effective_config("reranker").provider == "disabled" or not ctx.hits:
            ctx.hits = ctx.hits[:self.fallback_top_k]
            return ctx
        try:
            texts = await asyncio.to_thread(self._fetch_texts, ctx.hits)
            pairs = [(hit, text) for hit, text in zip(ctx.hits, texts) if text]
            if not pairs:
                ctx.hits = ctx.hits[:self.fallback_top_k]
                return ctx
            reranker = get_provider("reranker")
            scores = await reranker.rerank(ctx.question,
                                           [text for _, text in pairs])
            ranked = [hit for _, (hit, _) in
                      sorted(zip(scores, pairs), key=lambda x: x[0],
                             reverse=True)]
            ctx.hits = ranked[:self.top_k]
        except (RoleDisabled, Exception):  # noqa: BLE001 — degrade, don't die
            logger.exception("rerank failed; falling back to retrieval order")
            ctx.hits = ctx.hits[:self.fallback_top_k]
        return ctx

    @staticmethod
    def _fetch_texts(hits) -> list[str | None]:
        """Candidate text per hit: chunk text / record text_repr / table
        summary — the same strings that were embedded."""
        from tablerag.storage.db import session_scope
        from tablerag.storage.orm import Chunk, Record, TableElement
        from tablerag.storage.qdrant import (
            COLLECTION_CHUNKS,
            COLLECTION_RECORDS,
        )

        chunk_ids, record_ids, summary_ids = [], [], []
        for hit in hits:
            collection = hit.payload.get("_collection")
            if collection == COLLECTION_CHUNKS and hit.payload.get("chunk_id"):
                chunk_ids.append(uuid.UUID(hit.payload["chunk_id"]))
            elif collection == COLLECTION_RECORDS and hit.payload.get("record_id"):
                record_ids.append(uuid.UUID(hit.payload["record_id"]))
            elif hit.payload.get("element_id"):
                summary_ids.append(uuid.UUID(hit.payload["element_id"]))

        with session_scope() as s:
            chunks = {c.id: c.text for c in
                      s.query(Chunk).filter(Chunk.id.in_(chunk_ids))} \
                if chunk_ids else {}
            records = {r.id: r.text_repr for r in
                       s.query(Record).filter(Record.id.in_(record_ids))} \
                if record_ids else {}
            summaries = {t.element_id: t.summary for t in
                         s.query(TableElement).filter(
                             TableElement.element_id.in_(summary_ids))} \
                if summary_ids else {}

        texts: list[str | None] = []
        for hit in hits:
            collection = hit.payload.get("_collection")
            if collection == COLLECTION_CHUNKS:
                key = hit.payload.get("chunk_id")
                texts.append(chunks.get(uuid.UUID(key)) if key else None)
            elif collection == COLLECTION_RECORDS:
                key = hit.payload.get("record_id")
                texts.append(records.get(uuid.UUID(key)) if key else None)
            else:
                key = hit.payload.get("element_id")
                texts.append(summaries.get(uuid.UUID(key)) if key else None)
        return texts


class PassthroughRerank(Rerank):
    """Backward-compatible alias (Phase 1 name); same degrade-to-truncate
    behavior when the reranker role is disabled."""
