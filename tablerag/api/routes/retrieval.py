"""Dify-compatible External Knowledge API: raw retrieval, per KB, by API key.

https://docs.dify.ai/en/use-dify/knowledge/external-knowledge-api

The only other prefix `auth_middleware` lets through without an identity
besides `/api/embed` — same shape, same reasoning: a key stands in for one KB,
checked inside the route, and a wrong/missing key answers 404 rather than 403
so it never confirms the KB exists.

Unlike `/api/embed` this hands back raw retrieved text, not a generated
answer — it exists so another RAG platform (Dify, or anything speaking this
same contract) can use a LedgerRAG KB as its retrieval backend. Off by
default: a KB must have a key minted for it via `POST
/api/kbs/{kb_id}/retrieval-key` before this endpoint answers anything but 404.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from tablerag.core.config import get_settings
from tablerag.core.schemas import ExternalRecord, ExternalRetrievalRequest
from tablerag.query.pipeline import QueryContext
from tablerag.query.steps.assemble import AssembleContext
from tablerag.query.steps.rerank import Rerank
from tablerag.query.steps.retrieve import Retrieve
from tablerag.query.steps.router import SingleKBRouter
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])


def _error(status_code: int, error_code: int, error_msg: str) -> JSONResponse:
    return JSONResponse(status_code=status_code,
                        content={"error_code": error_code, "error_msg": error_msg})


def _bearer_token(authorization: str) -> str:
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix):].strip()
    return ""


@router.post("/{kb_id}/retrieval")
async def external_retrieval(kb_id: uuid.UUID, body: ExternalRetrievalRequest,
                             authorization: str = Header(default="")):
    token = _bearer_token(authorization)

    def resolve():
        with session_scope() as s:
            kb = repo.get_kb_by_retrieval_key(s, token)
            if kb is None or kb.id != kb_id:
                return None
            return kb.id, (kb.config or {}).get("locale")

    resolved = await asyncio.to_thread(resolve)
    if resolved is None:
        return _error(404, 1002, "Authorization failed. Please check your API key.")
    _, locale = resolved

    setting = body.retrieval_setting
    try:
        settings = get_settings()
        ctx = QueryContext(kb_id=kb_id, question=body.query, locale=locale)
        for step in (SingleKBRouter(),
                     Retrieve(top_k=settings.retrieve_candidates),
                     Rerank(top_k=setting.top_k, fallback_top_k=setting.top_k),
                     AssembleContext()):
            ctx = await step.run(ctx)
    except Exception:  # noqa: BLE001 — never leak internals to another app
        logger.exception("external retrieval failed (kb=%s)", kb_id)
        return _error(500, 2001, "internal error")

    records = [
        ExternalRecord(
            content=source.content, score=citation.score,
            title=f"{citation.filename} (p.{citation.page})",
            metadata={
                "doc_id": str(citation.doc_id), "element_id": str(citation.element_id),
                "chunk_id": str(citation.chunk_id) if citation.chunk_id else None,
                "page": citation.page, "kind": citation.kind,
                "confidence": citation.confidence, "needs_review": citation.needs_review,
                "crop_image_path": citation.crop_image_path,
            })
        for citation, source in zip(ctx.citations, ctx.sources)
        if citation.score >= setting.score_threshold
    ][:setting.top_k]
    return {"records": [r.model_dump() for r in records]}
