"""Rerank step (Phase 4): reorder the hybrid candidate pool with the
`reranker` model role (e.g. bge-reranker-v2-m3 behind a TEI/openai_compat
endpoint) and keep the best few for context.

The role is disabled by default — then this step cuts the pool to
`fallback_top_k`, giving each retrieved document its best block first so no
single long document owns the head of the context (see diversify_by_document).
When enabled but unreachable, it degrades the same way instead of failing the
question (honest degradation, never a dead chat)."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
import uuid

from tablerag.models.registry import (
    RoleDisabled,
    effective_config,
    get_provider,
    note_role_failure,
    note_role_success,
)
from tablerag.query.pipeline import QueryContext
from tablerag.storage.qdrant import COLLECTION_CHUNKS

logger = logging.getLogger(__name__)


def diversify_by_document(hits: list, k: int) -> list:
    """Take the best k hits, but give every retrieved document its best block
    before any document takes a second slot.

    Without a reranker the pool is cut by raw fusion score, and a long document
    can occupy the whole head of the context. Measured on the box: when the
    document holding the answer landed at rank 4-6 the model answered from the
    document at rank 1 instead — 5 failures out of 5; when it landed at rank 2
    the answer was right 4 times out of 4. Recall was never the problem, the
    ordering was.

    Score order is otherwise preserved, so this only ever promotes a document's
    FIRST block; it never reorders blocks within a document.
    """
    first_of_doc, rest = [], []
    seen: set[str] = set()
    for hit in hits:  # already sorted by score desc
        doc_id = (hit.payload or {}).get("doc_id")
        if doc_id is not None and doc_id not in seen:
            seen.add(doc_id)
            first_of_doc.append(hit)
        else:
            rest.append(hit)
    return (first_of_doc + rest)[:k]


def collection_mix(hits) -> str:
    """Which collections a set of hits came from, e.g. "chunks=11 records=1".

    The table sub-pipeline is this product's reason to exist, and a run on the
    EPSENS corpus put a table in the context for one question out of seventeen.
    Two causes need opposite fixes - records never retrieved, or retrieved and
    outranked by prose - and the pool composition before and after ranking is
    what separates them.
    """
    counts = Counter(h.payload.get("_collection", "?") for h in hits)
    return " ".join(f"{name}={n}" for name, n in sorted(counts.items())) or "empty"


# where the cross-encoder's judgement is kept. Not on hit.score: that is the
# hybrid-fusion score, the reason this candidate was in the pool at all, and it
# is worth keeping. The two answer different questions - "several searches
# agreed to look here" versus "this passage answers what was asked" - and only
# the second is fit to show a reader as relevance.
_RERANK_SCORE = "_rerank_score"


def carry_rerank_score(hit, score: float) -> None:
    hit.payload[_RERANK_SCORE] = float(score)


def relevance_of(hit) -> float:
    """How well this source answered, falling back to how it was found.

    The reranker is pluggable and may be disabled; a source list must still be
    ordered by something meaningful rather than by zero."""
    value = hit.payload.get(_RERANK_SCORE)
    return float(value) if value is not None else float(hit.score)


def reserve_structured_slots(ranked: list, top_k: int, reserve: int) -> list:
    """Keep the top `top_k`, but never let prose take every slot.

    Measured on the box: a candidate pool of a third chunks, a third records and
    a third table summaries came out of the cross-encoder as eight chunks and
    nothing else, on ten queries out of ten. bge-reranker-v2-m3 scores whether a
    PASSAGE answers a question, and a table row - "Portefeuille | 1 mois: -2,58
    | 2021: 9,42" - is not a passage however exactly it holds the answer. The
    table sub-pipeline was therefore absent from the context on sixteen of
    seventeen questions, and table questions were answered off page prose.

    So `reserve` slots go to the best record/summary hits when any exist. This
    is the same admission `diversify_by_document` already makes: a pure ranking
    can produce a context that is uniform and therefore poor.

    Rank order is preserved. Position IS rank downstream, and re-ordering here
    would silently undo the reranker's decision.
    """
    kept = list(ranked[:top_k])
    if reserve <= 0 or len(ranked) <= top_k:
        return kept

    def structured(hit) -> bool:
        return hit.payload.get("_collection") != COLLECTION_CHUNKS

    have = sum(1 for hit in kept if structured(hit))
    waiting = [hit for hit in ranked[top_k:] if structured(hit)]
    chosen = {id(hit) for hit in kept}
    for candidate in waiting[:max(0, reserve - have)]:
        # give up the weakest prose slot, not the strongest
        for index in range(len(kept) - 1, -1, -1):
            if not structured(kept[index]):
                chosen.discard(id(kept.pop(index)))
                break
        else:
            break
        chosen.add(id(candidate))
    return [hit for hit in ranked if id(hit) in chosen]


class Rerank:
    def __init__(self, top_k: int = 8, fallback_top_k: int = 12,
                 reserve_structured: int = 0):
        self.top_k = top_k
        self.fallback_top_k = fallback_top_k
        self.reserve_structured = reserve_structured

    async def run(self, ctx: QueryContext) -> QueryContext:
        if effective_config("reranker").provider == "disabled" or not ctx.hits:
            ctx.hits = diversify_by_document(ctx.hits, self.fallback_top_k)
            return ctx
        try:
            texts = await asyncio.to_thread(self._fetch_texts, ctx.hits)
            pairs = [(hit, text) for hit, text in zip(ctx.hits, texts) if text]
            if not pairs:
                ctx.hits = diversify_by_document(ctx.hits, self.fallback_top_k)
                return ctx
            reranker = get_provider("reranker")
            scores = await reranker.rerank(ctx.search_query,
                                           [text for _, text in pairs])
            for score, (hit, _) in zip(scores, pairs):
                carry_rerank_score(hit, score)
            ranked = [hit for _, (hit, _) in
                      sorted(zip(scores, pairs), key=lambda x: x[0],
                             reverse=True)]
            kept = reserve_structured_slots(ranked, self.top_k,
                                            self.reserve_structured)
            logger.info("rerank: %d candidates (%s) -> %d kept (%s)",
                        len(ctx.hits), collection_mix(ctx.hits),
                        len(kept), collection_mix(kept))
            ctx.hits = kept
            note_role_success("reranker")
        except (RoleDisabled, Exception) as exc:  # noqa: BLE001 — degrade, don't die
            logger.exception("rerank failed; falling back to retrieval order")
            # a role the operator configured must not fail in silence: this is
            # the difference between "no reranker" and "a reranker that is
            # broken", and the pipeline behaves identically in both
            note_role_failure("reranker", exc)
            ctx.hits = diversify_by_document(ctx.hits, self.fallback_top_k)
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
