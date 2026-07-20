"""Full re-index migration (SPEC Phase 4): recreate the Qdrant collections
with the current schema (dense + sparse hybrid) and re-embed EVERYTHING from
Postgres — chunks, records, table summaries. No re-parsing: principle #1
(storage is the contract) means the parsed truth lives in Postgres and only
the vectors are rebuilt.

Run inside the api container (services aren't exposed to the host):

    docker compose exec api python -m tablerag.scripts.reindex_all

Needs the embedder endpoint to be reachable. Existing chat keeps working on
the old index until the recreate happens; ingestion during the migration is
not recommended.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from tablerag.core.logging import setup_logging
from tablerag.ingestion.html_tables import html_to_text
from tablerag.ingestion.table_pipeline import build_text_repr
from tablerag.models.registry import get_provider
from tablerag.storage.db import session_scope
from tablerag.storage.orm import Chunk, Document, Element, Record, TableElement
from tablerag.storage.qdrant import (
    COLLECTION_CHUNKS,
    COLLECTION_RECORDS,
    COLLECTION_TABLE_SUMMARIES,
    get_vector_store,
)

logger = logging.getLogger(__name__)

BATCH = 32


def _collect_jobs() -> list[tuple[str, object, str, dict]]:
    """(collection, point_id, text, payload) for every indexable row."""
    jobs: list[tuple[str, object, str, dict]] = []
    with session_scope() as s:
        docs = {d.id: d for d in s.scalars(select(Document))}
        elements = {e.id: e for e in s.scalars(select(Element))}

        def base(element_id):
            element = elements.get(element_id)
            doc = docs.get(element.doc_id) if element else None
            if element is None or doc is None:
                return None
            return {"kb_id": str(doc.kb_id), "doc_id": str(doc.id),
                    "element_id": str(element_id)}

        for chunk in s.scalars(select(Chunk)):
            payload = base(chunk.element_id)
            if payload:
                jobs.append((COLLECTION_CHUNKS, chunk.id, chunk.text,
                             {**payload, "chunk_id": str(chunk.id)}))
        rebuilt = n_records = 0
        for record in s.scalars(select(Record)):
            n_records += 1
            # recompute from the stored dimensions/metrics so rows indexed by
            # an older build adopt the current representation without a
            # re-parse (principle #1: the parsed truth is already in Postgres)
            text = build_text_repr(record.dimensions or {}, record.metrics or {},
                                   record.raw_values or {})
            if text and text != record.text_repr:
                record.text_repr = text
                rebuilt += 1
            payload = base(record.table_element_id)
            if payload:
                jobs.append((COLLECTION_RECORDS, record.id,
                             record.text_repr or text,
                             {**payload, "record_id": str(record.id)}))
        # always report: a silent step makes "did not run" and "nothing to do"
        # look identical, which is exactly how a stale container hides itself
        logger.info("reindex: %d records, %d text_repr rewritten", n_records,
                    rebuilt)
        if n_records and not rebuilt:
            logger.warning(
                "reindex: no record text changed — either this build is stale "
                "or the records carry no dimension names")
        for table in s.scalars(select(TableElement)):
            element = elements.get(table.element_id)
            if element is None or (element.meta or {}).get("unusable"):
                continue
            # same fallback as ingest: a table with no LLM summary (failed /
            # flagged parse) is indexed by its raw cell text so it stays
            # retrievable and can surface as a LOW CONFIDENCE source
            text = table.summary or html_to_text(table.html)[:2000]
            if not text:
                continue
            payload = base(table.element_id)
            if payload:
                jobs.append((COLLECTION_TABLE_SUMMARIES, table.element_id,
                             text, payload))
    return jobs


async def run() -> None:
    setup_logging()
    store = get_vector_store()
    jobs = _collect_jobs()
    logger.info("reindex: %d vectors to rebuild", len(jobs))

    logger.info("recreating collections with hybrid (dense+sparse) schema...")
    store.recreate_collections()

    embedder = get_provider("embedder")
    done = 0
    for start in range(0, len(jobs), BATCH):
        batch = jobs[start:start + BATCH]
        vectors = await embedder.embed([j[2] for j in batch])
        by_collection: dict[str, list] = {}
        for job, vector in zip(batch, vectors):
            by_collection.setdefault(job[0], []).append((job, vector))
        for collection, items in by_collection.items():
            store.upsert(
                collection,
                ids=[j[1] for j, _ in items],
                dense=[v.dense for _, v in items],
                payloads=[j[3] for j, _ in items],
                texts=[j[2] for j, _ in items])
        done += len(batch)
        logger.info("reindex: %d/%d", done, len(jobs))
    logger.info("reindex complete — hybrid retrieval is now active")


if __name__ == "__main__":
    asyncio.run(run())
