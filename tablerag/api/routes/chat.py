"""Chat endpoint: SSE streaming from day one (SPEC Phase 1 — retrofitting
streaming later is painful, so it ships in the skeleton)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from tablerag.core.schemas import ChatRequest
from tablerag.query.pipeline import QueryContext, default_pipeline
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/kbs/{kb_id}/chat")
async def chat(kb_id: uuid.UUID, body: ChatRequest) -> StreamingResponse:
    def prepare() -> uuid.UUID:
        with session_scope() as s:
            if repo.get_kb(s, kb_id) is None:
                raise HTTPException(404, "knowledge base not found")
            session = repo.get_or_create_session(s, kb_id, body.session_id)
            repo.add_message(s, session.id, "user", body.question)
            return session.id

    session_id = await asyncio.to_thread(prepare)

    async def event_stream():
        ctx = QueryContext(kb_id=kb_id, question=body.question)
        try:
            async for kind, payload in default_pipeline().stream(ctx):
                if kind == "citations":
                    yield _sse({"type": "citations",
                                "citations": [c.model_dump(mode="json")
                                              for c in payload]})
                elif kind == "token":
                    yield _sse({"type": "token", "content": payload})

            def persist() -> uuid.UUID:
                with session_scope() as s:
                    msg = repo.add_message(
                        s, session_id, "assistant", ctx.answer,
                        citations=[c.model_dump(mode="json") for c in ctx.citations],
                        verification=ctx.verification)
                    return msg.id

            message_id = await asyncio.to_thread(persist)
            yield _sse({"type": "done", "session_id": str(session_id),
                        "message_id": str(message_id)})
        except Exception:  # noqa: BLE001 — stream errors must reach the client readably
            logger.exception("chat pipeline failed (kb=%s)", kb_id)
            yield _sse({"type": "error",
                        "message": "The assistant could not answer this question "
                                   "due to an internal error. Please try again."})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
