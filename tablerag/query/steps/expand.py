"""Pull in the elements a retrieved source needs in order to be readable.

Placed AFTER Rerank so it cannot dilute ranking — the reranker judges what
search found, not what we then decided to bring along — and BEFORE
AssembleContext so everything it adds is subject to the same character budget
and is sacrificed first when that budget binds.

Expanded items are appended after the ranked hits and marked, so they take
their own citation numbers. Folding them into the winning source instead would
keep citation counts stable and make a fact from page 6 cite page 5; the
traceability principle is not worth a quieter gate.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from tablerag.query.neighbours import choose_neighbours
from tablerag.query.pipeline import QueryContext
from tablerag.storage.db import session_scope
from tablerag.storage.repositories import get_page_elements

logger = logging.getLogger(__name__)


class ExpandNeighbours:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    async def run(self, ctx: QueryContext) -> QueryContext:
        if not self.enabled or not ctx.hits:
            return ctx
        try:
            extra = await asyncio.to_thread(self._extra, ctx.hits)
            logger.info("expand: %d ranked hit(s) pulled in %d neighbour(s)",
                        len(ctx.hits), len(extra))
            ctx.hits = ctx.hits + extra
        except Exception:  # noqa: BLE001 — an answer must survive this
            logger.exception("neighbour expansion failed (non-fatal)")
        return ctx

    @staticmethod
    def _extra(hits: list) -> list:
        doc_ids, winners = set(), []
        for hit in hits:
            if raw := hit.payload.get("doc_id"):
                doc_ids.add(uuid.UUID(raw))
            if raw := hit.payload.get("element_id"):
                winners.append(uuid.UUID(raw))
        if not winners:
            return []
        with session_scope() as s:
            candidates = get_page_elements(s, sorted(doc_ids, key=str))
        by_id = {c.element_id: c for c in candidates}
        extra = []
        for element_id in choose_neighbours(candidates, winners):
            candidate = by_id[element_id]
            extra.append(type(hits[0])(
                id=element_id, score=0.0,
                payload={"element_id": str(element_id),
                         "doc_id": str(candidate.doc_id),
                         # assemble routes on this: a table element hydrates to
                         # its parent table, a text or figure element to its
                         # chunks. Without it every expansion would be looked up
                         # as a table and text neighbours would silently vanish.
                         "element_type": candidate.type,
                         "_collection": "expanded", "_expanded": True}))
        return extra
