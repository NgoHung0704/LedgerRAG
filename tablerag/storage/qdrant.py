"""Vector store wrapper (Qdrant).

Three collections from day one (SPEC §3.2): `chunks` (Phase 1), `records` and
`table_summaries` (filled from Phase 2). Every point carries
{kb_id, doc_id, element_id, (chunk_id | record_id)} for payload filtering and
provenance. Vectors are *named* ("dense") from the start so Phase 4 can add a
sparse vector without re-creating collections.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from tablerag.core.config import get_settings

COLLECTION_CHUNKS = "chunks"
COLLECTION_RECORDS = "records"
COLLECTION_TABLE_SUMMARIES = "table_summaries"
ALL_COLLECTIONS = (COLLECTION_CHUNKS, COLLECTION_RECORDS, COLLECTION_TABLE_SUMMARIES)

DENSE = "dense"


@dataclass
class SearchHit:
    id: uuid.UUID
    score: float
    payload: dict


class VectorStore:
    def __init__(self, url: str | None = None, dim: int | None = None):
        settings = get_settings()
        self.client = QdrantClient(url=url or settings.qdrant_url)
        self.dim = dim or settings.embedding_dim

    def ensure_collections(self) -> None:
        for name in ALL_COLLECTIONS:
            if not self.client.collection_exists(name):
                self.client.create_collection(
                    collection_name=name,
                    vectors_config={
                        DENSE: qm.VectorParams(size=self.dim,
                                               distance=qm.Distance.COSINE),
                    },
                )
                for field in ("kb_id", "doc_id"):
                    self.client.create_payload_index(
                        collection_name=name, field_name=field,
                        field_schema=qm.PayloadSchemaType.KEYWORD)

    def upsert(self, collection: str, ids: list[uuid.UUID],
               dense: list[list[float]], payloads: list[dict]) -> None:
        points = [
            qm.PointStruct(id=str(pid), vector={DENSE: vec}, payload=payload)
            for pid, vec, payload in zip(ids, dense, payloads)
        ]
        self.client.upsert(collection_name=collection, points=points, wait=True)

    def search(self, collection: str, dense: list[float],
               kb_ids: list[uuid.UUID], top_k: int) -> list[SearchHit]:
        flt = qm.Filter(must=[
            qm.FieldCondition(key="kb_id",
                              match=qm.MatchAny(any=[str(k) for k in kb_ids])),
        ])
        result = self.client.query_points(
            collection_name=collection,
            query=dense, using=DENSE,
            query_filter=flt, limit=top_k, with_payload=True)
        return [SearchHit(id=uuid.UUID(str(p.id)), score=p.score,
                          payload=p.payload or {})
                for p in result.points]

    def delete_doc(self, doc_id: uuid.UUID) -> None:
        """Idempotent reprocessing: drop every vector belonging to a document."""
        flt = qm.Filter(must=[
            qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=str(doc_id))),
        ])
        for name in ALL_COLLECTIONS:
            if self.client.collection_exists(name):
                self.client.delete(collection_name=name,
                                   points_selector=qm.FilterSelector(filter=flt),
                                   wait=True)


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
