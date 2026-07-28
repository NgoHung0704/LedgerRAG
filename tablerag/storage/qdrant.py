"""Vector store wrapper (Qdrant).

Three collections from day one (SPEC §3.2): `chunks` (Phase 1), `records` and
`table_summaries` (filled from Phase 2). Every point carries
{kb_id, doc_id, element_id, (chunk_id | record_id)} for payload filtering and
provenance.

Phase 4 hybrid: each point stores a named dense vector plus a named sparse
lexical vector (term frequencies from core/sparse.py; Qdrant applies IDF
server-side). Queries fuse both with native RRF. Collections created before
the sparse upgrade lack the sparse config — searches degrade gracefully to
dense-only until `python -m tablerag.scripts.reindex_all` migrates them
(re-embed only, no re-parse — principle #1 pays off here).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache

import httpx
from qdrant_client import QdrantClient
from qdrant_client import models as qm
from qdrant_client.http.exceptions import ResponseHandlingException

from tablerag.core.config import get_settings
from tablerag.core.sparse import sparse_vector

logger = logging.getLogger(__name__)

# upserts are batched so each request stays small under a bulk upload, and each
# write is retried on a transient timeout so a busy Qdrant is waited out rather
# than throwing an exception that makes the ingest task re-parse the whole
# document (expensive for scanned PDFs) — the death spiral behind mass
# "ResponseHandlingException: timed out" failures on a bulk upload.
_UPSERT_BATCH = 256
_QDRANT_ATTEMPTS = 4


def _retry_qdrant(op, what: str):
    delay = 2.0
    for attempt in range(_QDRANT_ATTEMPTS):
        try:
            return op()
        except (ResponseHandlingException, httpx.TransportError) as e:
            if attempt == _QDRANT_ATTEMPTS - 1:
                raise
            logger.warning("qdrant %s failed (%s: %s); retry %d/%d in %.0fs",
                           what, type(e).__name__, e, attempt + 1,
                           _QDRANT_ATTEMPTS, delay)
            time.sleep(delay)
            delay = min(30.0, delay * 2)

COLLECTION_CHUNKS = "chunks"
COLLECTION_RECORDS = "records"
COLLECTION_TABLE_SUMMARIES = "table_summaries"
ALL_COLLECTIONS = (COLLECTION_CHUNKS, COLLECTION_RECORDS, COLLECTION_TABLE_SUMMARIES)

DENSE = "dense"
SPARSE = "sparse"


@dataclass
class SearchHit:
    id: uuid.UUID
    score: float
    payload: dict


class VectorStore:
    def __init__(self, url: str | None = None, dim: int | None = None):
        settings = get_settings()
        # timeout is explicit: the client defaults to 5s, too tight for a
        # synchronous upsert(wait=True) against a Qdrant busy with a bulk upload
        # (see settings.qdrant_timeout).
        self.client = QdrantClient(url=url or settings.qdrant_url,
                                   timeout=settings.qdrant_timeout)
        self.dim = dim or settings.embedding_dim
        self._sparse_ready: dict[str, bool] = {}

    def ensure_collections(self) -> None:
        for name in ALL_COLLECTIONS:
            if not self.client.collection_exists(name):
                self.client.create_collection(
                    collection_name=name,
                    vectors_config={
                        DENSE: qm.VectorParams(size=self.dim,
                                               distance=qm.Distance.COSINE),
                    },
                    sparse_vectors_config={
                        SPARSE: qm.SparseVectorParams(
                            modifier=qm.Modifier.IDF),
                    },
                )
                for field in ("kb_id", "doc_id", "element_id"):
                    self.client.create_payload_index(
                        collection_name=name, field_name=field,
                        field_schema=qm.PayloadSchemaType.KEYWORD)
                self._sparse_ready[name] = True

    def recreate_collections(self) -> None:
        """Migration helper: drop and recreate with the current schema
        (dense + sparse). Callers must re-upsert everything afterwards."""
        for name in ALL_COLLECTIONS:
            if self.client.collection_exists(name):
                self.client.delete_collection(name)
        self._sparse_ready.clear()
        self.ensure_collections()

    def has_sparse(self, collection: str) -> bool:
        """Old collections (pre-hybrid) have no sparse config; degrade to
        dense-only for them instead of failing queries/upserts."""
        if collection not in self._sparse_ready:
            try:
                info = self.client.get_collection(collection)
                sparse_cfg = getattr(info.config.params, "sparse_vectors", None)
                self._sparse_ready[collection] = bool(
                    sparse_cfg and SPARSE in sparse_cfg)
            except Exception:  # noqa: BLE001
                return False
        return self._sparse_ready[collection]

    def upsert(self, collection: str, ids: list[uuid.UUID],
               dense: list[list[float]], payloads: list[dict],
               texts: list[str] | None = None) -> None:
        """texts (when given, aligned with ids) produce the sparse lexical
        vector for hybrid search."""
        with_sparse = texts is not None and self.has_sparse(collection)
        points = []
        for i, (pid, vec, payload) in enumerate(zip(ids, dense, payloads)):
            vector: dict = {DENSE: vec}
            if with_sparse:
                indices, values = sparse_vector(texts[i])
                if indices:
                    vector[SPARSE] = qm.SparseVector(indices=indices,
                                                     values=values)
            points.append(qm.PointStruct(id=str(pid), vector=vector,
                                         payload=payload))
        for start in range(0, len(points), _UPSERT_BATCH):
            batch = points[start:start + _UPSERT_BATCH]
            _retry_qdrant(
                lambda b=batch: self.client.upsert(
                    collection_name=collection, points=b, wait=True),
                what=f"upsert {collection} ({len(batch)} pts)")

    def search(self, collection: str, dense: list[float],
               kb_ids: list[uuid.UUID], top_k: int,
               query_text: str | None = None) -> list[SearchHit]:
        """Hybrid dense+sparse with native RRF fusion when query_text is given
        and the collection supports sparse; dense-only otherwise."""
        flt = qm.Filter(must=[
            qm.FieldCondition(key="kb_id",
                              match=qm.MatchAny(any=[str(k) for k in kb_ids])),
        ])
        if query_text and self.has_sparse(collection):
            indices, values = sparse_vector(query_text)
            if indices:
                result = self.client.query_points(
                    collection_name=collection,
                    prefetch=[
                        qm.Prefetch(query=dense, using=DENSE,
                                    filter=flt, limit=top_k),
                        qm.Prefetch(
                            query=qm.SparseVector(indices=indices,
                                                  values=values),
                            using=SPARSE, filter=flt, limit=top_k),
                    ],
                    query=qm.FusionQuery(fusion=qm.Fusion.RRF),
                    limit=top_k, with_payload=True)
                return [SearchHit(id=uuid.UUID(str(p.id)), score=p.score,
                                  payload=p.payload or {})
                        for p in result.points]
        result = self.client.query_points(
            collection_name=collection,
            query=dense, using=DENSE,
            query_filter=flt, limit=top_k, with_payload=True)
        return [SearchHit(id=uuid.UUID(str(p.id)), score=p.score,
                          payload=p.payload or {})
                for p in result.points]

    def delete_doc(self, doc_id: uuid.UUID) -> None:
        """Idempotent reprocessing: drop every vector belonging to a document."""
        self._delete_by(key="doc_id", value=str(doc_id))

    def delete_element(self, element_id: uuid.UUID) -> None:
        """Review flow 'mark unusable' / manual edits: remove an element's
        vectors from retrieval; Postgres rows and the crop image stay."""
        self._delete_by(key="element_id", value=str(element_id))

    def delete_kb(self, kb_id: uuid.UUID) -> None:
        """Drop every vector of a KB in one filtered delete (payloads carry
        kb_id) — used when deleting a whole knowledge base."""
        self._delete_by(key="kb_id", value=str(kb_id))

    def delete_docs(self, doc_ids: list[uuid.UUID]) -> None:
        """Batch delete for the UI's multi-select: every vector of many
        documents in ONE filtered delete per collection (MatchAny on doc_id),
        instead of N×3 per-document round-trips. A 40-document delete stays a
        handful of calls, not hundreds — so the request can't outrun the
        browser's fetch timeout (the 'NetworkError' the bulk delete hit)."""
        if not doc_ids:
            return
        self._delete_by_match(qm.FieldCondition(
            key="doc_id",
            match=qm.MatchAny(any=[str(d) for d in doc_ids])))

    def _delete_by(self, key: str, value: str) -> None:
        self._delete_by_match(
            qm.FieldCondition(key=key, match=qm.MatchValue(value=value)))

    def _delete_by_match(self, condition: "qm.FieldCondition") -> None:
        flt = qm.Filter(must=[condition])
        for name in ALL_COLLECTIONS:
            if self.client.collection_exists(name):
                _retry_qdrant(
                    lambda n=name: self.client.delete(
                        collection_name=n,
                        points_selector=qm.FilterSelector(filter=flt),
                        wait=True),
                    what=f"delete from {name}")


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
