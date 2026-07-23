"""Chat endpoint: SSE streaming from day one (SPEC Phase 1 — retrofitting
streaming later is painful, so it ships in the skeleton)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from tablerag.core.auth import User, current_user
from tablerag.core.schemas import ChatRequest, FeedbackRequest, MultiChatRequest
from tablerag.query.pipeline import QueryContext, default_pipeline
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/messages/{message_id}/feedback")
async def message_feedback(message_id: uuid.UUID, body: FeedbackRequest) -> dict:
    """👍/👎 on an answer (Phase 5). Feeds the eval-as-asset loop: thumbs-down
    answers are the dogfood questions worth adding to the eval set."""
    def save() -> int | None:
        with session_scope() as s:
            return repo.set_feedback(s, message_id, body.value)

    return {"value": await asyncio.to_thread(save)}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _instructions(s, kb_instructions: str | None = None) -> str:
    """Operator guidance appended to the chat system prompt: the global setting
    plus (optionally) a single KB's own, joined. Empty when nothing is set."""
    stored = repo.get_setting(s, repo.CHAT_INSTRUCTIONS_SETTING) or {}
    parts = [stored.get("text", ""), kb_instructions or ""]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


@router.post("/kbs/{kb_id}/chat")
async def chat(kb_id: uuid.UUID, body: ChatRequest,
               user: User = Depends(current_user)) -> StreamingResponse:
    def prepare() -> tuple[uuid.UUID, str | None, bool,
                           list[tuple[str, str]], str]:
        with session_scope() as s:
            kb = repo.get_kb(s, kb_id)
            if kb is None:
                raise HTTPException(404, "knowledge base not found")
            kb_config = kb.config or {}
            locale = kb_config.get("locale")
            # verification default ON for KBs that contain tables (SPEC Phase 4)
            verify = body.verify
            if verify is None:
                verify = kb_config.get("verify")
            session = repo.get_or_create_session(s, kb_id, body.session_id)
            # load the thread BEFORE recording this turn, so history is the
            # prior turns only (multi-turn: the pipeline condenses follow-ups)
            history = repo.get_recent_messages(s, session.id)
            repo.add_message(s, session.id, "user", body.question)
            repo.log_audit(s, user.username, "query", kb_id=kb_id,
                           detail={"question": body.question[:200]})
            # operator guidance: global + this KB's own, both appended (never
            # overriding the safety rules — see generate.build_system_prompt)
            extra = _instructions(s, kb_config.get("instructions"))
            return session.id, locale, verify, history, extra

    session_id, locale, verify, history, extra = await asyncio.to_thread(prepare)

    async def event_stream():
        ctx = QueryContext(kb_id=kb_id, question=body.question, locale=locale,
                           history=history, extra_instructions=extra)
        try:
            async for kind, payload in default_pipeline(verify=verify).stream(ctx):
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
                        "message_id": str(message_id),
                        # the standalone query a follow-up was condensed to
                        # (== question on a first turn); surfaced for eval-followup
                        "search_question": ctx.search_question,
                        "verification": ctx.verification})
        except Exception:  # noqa: BLE001 — stream errors must reach the client readably
            logger.exception("chat pipeline failed (kb=%s)", kb_id)
            yield _sse({"type": "error",
                        "message": "The assistant could not answer this question "
                                   "due to an internal error. Please try again."})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.post("/chat")
async def chat_multi(body: MultiChatRequest,
                     user: User = Depends(current_user)) -> StreamingResponse:
    """Phase 5 multi-KB chat: the LLMRouter picks which KB(s) to search from
    their descriptions, or the caller pins `kb_ids` to override it. Same SSE
    contract as the scoped endpoint, plus a `routing` field on `done`."""
    from tablerag.query.steps.router import LLMRouter

    def prepare() -> tuple[list[uuid.UUID], str | None,
                           list[tuple[str, str]], str]:
        with session_scope() as s:
            kbs = repo.list_kbs(s)
            if not kbs:
                raise HTTPException(404, "no knowledge bases exist")
            by_id = {kb.id: kb for kb in kbs}
            pinned = body.kb_ids or []
            unknown = [k for k in pinned if k not in by_id]
            if unknown:
                raise HTTPException(404, f"unknown kb_ids: {unknown}")
            # locale for number verification only when it is unambiguous:
            # a shared locale across the searched KBs, else conservative None
            scope = [by_id[k] for k in pinned] if pinned else kbs
            locales = {(kb.config or {}).get("locale") for kb in scope}
            locale = locales.pop() if len(locales) == 1 else None
            # continuing a thread: load its prior turns for follow-up condensing.
            # this turn's messages are written later in persist(), so they are
            # excluded. a first turn (no session_id) has no history.
            history = (repo.get_recent_messages(s, body.session_id)
                       if body.session_id else [])
            # global guidance always applies; a KB's own only when the search is
            # pinned to exactly that one KB (across several it is ambiguous)
            kb_instr = (by_id[pinned[0]].config or {}).get("instructions") \
                if len(pinned) == 1 else None
            extra = _instructions(s, kb_instr)
            return pinned, locale, history, extra

    pinned, locale, history, extra = await asyncio.to_thread(prepare)

    async def event_stream():
        # kb_id is unused when pinned/routed drives retrieval; keep a stable
        # placeholder (first pinned, else a nil uuid resolved after routing)
        ctx = QueryContext(kb_id=pinned[0] if pinned else uuid.UUID(int=0),
                           question=body.question, locale=locale,
                           pinned_kb_ids=pinned or None, history=history,
                           extra_instructions=extra)
        try:
            pipeline = default_pipeline(verify=body.verify, router=LLMRouter())
            async for kind, payload in pipeline.stream(ctx):
                if kind == "citations":
                    yield _sse({"type": "citations",
                                "citations": [c.model_dump(mode="json")
                                              for c in payload]})
                elif kind == "token":
                    yield _sse({"type": "token", "content": payload})

            def persist() -> tuple[uuid.UUID, uuid.UUID]:
                # a multi-KB session is grouped under the first searched KB
                rep_kb = ctx.routed_kb_ids[0] if ctx.routed_kb_ids else ctx.kb_id
                with session_scope() as s:
                    session = repo.get_or_create_session(s, rep_kb, body.session_id)
                    repo.add_message(s, session.id, "user", body.question)
                    repo.log_audit(
                        s, user.username, "query", kb_id=rep_kb,
                        detail={"question": body.question[:200],
                                "routing": (ctx.routing or {}).get("mode")})
                    msg = repo.add_message(
                        s, session.id, "assistant", ctx.answer,
                        citations=[c.model_dump(mode="json") for c in ctx.citations],
                        verification=ctx.verification)
                    return session.id, msg.id

            session_id, message_id = await asyncio.to_thread(persist)
            yield _sse({"type": "done", "session_id": str(session_id),
                        "message_id": str(message_id),
                        "routing": ctx.routing,
                        # the standalone query a follow-up was condensed to
                        # (== question on a first turn); surfaced for eval-followup
                        "search_question": ctx.search_question,
                        "verification": ctx.verification})
        except Exception:  # noqa: BLE001 — stream errors must reach the client
            logger.exception("multi-KB chat failed")
            yield _sse({"type": "error",
                        "message": "The assistant could not answer this question "
                                   "due to an internal error. Please try again."})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
