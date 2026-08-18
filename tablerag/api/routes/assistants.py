"""Assistants: chat apps with their own knowledge bases, prompt and threads.

A knowledge base is a corpus; an assistant is how someone talks to a chosen set
of them. Assistants REFERENCE knowledge bases (they never own documents), so KB
isolation — the founding idea — is untouched and one corpus can back several
assistants.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse

from tablerag.core.auth import User, current_user
from tablerag.core.schemas import (
    AssistantChatRequest,
    AssistantCreate,
    AssistantOut,
    AssistantUpdate,
    ConversationOut,
    ConversationRename,
)
from tablerag.query.pipeline import QueryContext, default_pipeline
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["assistants"])

TITLE_CHARS = 60


def escalation_contact(assistant_config: dict | None) -> str | None:
    """Who the reader is told to ask when an answer is flagged.

    The assistant's own setting, and nothing else. It has one fixed set of
    documents and one purpose, so there is nobody to be ambiguous with — which
    is why this moved here off the knowledge bases, where an assistant spanning
    an HR base and a finance base, each naming its own department, produced no
    contact at all and the reader got generic wording precisely when a name
    would have helped most.

    A stored blank is not a contact: it would reach the reader as "or contact ."
    """
    return ((assistant_config or {}).get("escalation_contact") or "").strip() or None


def _out(s, assistant) -> AssistantOut:
    kb_ids = repo.assistant_kb_ids(s, assistant.id)
    names = {kb.id: kb.name for kb in repo.list_kbs(s)}
    config = assistant.config or {}
    return AssistantOut(
        id=assistant.id, name=assistant.name, description=assistant.description,
        instructions=assistant.instructions, kb_ids=kb_ids,
        kb_names=[names.get(k, "?") for k in kb_ids],
        opening_message=config.get("opening_message", ""),
        verify=config.get("verify"),
        escalation_contact=config.get("escalation_contact", ""),
        created_at=assistant.created_at)


@router.get("/assistants", response_model=list[AssistantOut])
def list_assistants() -> list[AssistantOut]:
    with session_scope() as s:
        return [_out(s, a) for a in repo.list_assistants(s)]


@router.post("/assistants", response_model=AssistantOut, status_code=201)
def create_assistant(body: AssistantCreate,
                     user: User = Depends(current_user)) -> AssistantOut:
    config: dict = {"opening_message": body.opening_message.strip()}
    if body.verify is not None:
        config["verify"] = body.verify
    if body.escalation_contact.strip():
        config["escalation_contact"] = body.escalation_contact.strip()
    with session_scope() as s:
        assistant = repo.create_assistant(
            s, name=body.name.strip(), description=body.description.strip(),
            instructions=body.instructions.strip(), config=config,
            kb_ids=body.kb_ids)
        repo.log_audit(s, user.username, "assistant_create",
                       detail={"assistant": assistant.name,
                               "kbs": len(body.kb_ids)})
        return _out(s, assistant)


@router.get("/assistants/{assistant_id}", response_model=AssistantOut)
def get_assistant(assistant_id: uuid.UUID) -> AssistantOut:
    with session_scope() as s:
        assistant = repo.get_assistant(s, assistant_id)
        if assistant is None:
            raise HTTPException(404, "assistant not found")
        return _out(s, assistant)


@router.patch("/assistants/{assistant_id}", response_model=AssistantOut)
def update_assistant(assistant_id: uuid.UUID, body: AssistantUpdate,
                     user: User = Depends(current_user)) -> AssistantOut:
    with session_scope() as s:
        assistant = repo.get_assistant(s, assistant_id)
        if assistant is None:
            raise HTTPException(404, "assistant not found")
        if body.name is not None:
            assistant.name = body.name.strip()
        if body.description is not None:
            assistant.description = body.description.strip()
        if body.instructions is not None:
            assistant.instructions = body.instructions.strip()
        # JSONB mutation tracking: rebind a new dict, never mutate in place
        config = dict(assistant.config or {})
        if body.opening_message is not None:
            config["opening_message"] = body.opening_message.strip()
        if body.verify is not None:
            config["verify"] = body.verify
        if body.escalation_contact is not None:
            wanted = body.escalation_contact.strip()
            if wanted:
                config["escalation_contact"] = wanted
            else:
                config.pop("escalation_contact", None)  # cleared
        assistant.config = config
        if body.kb_ids is not None:
            repo.set_assistant_kbs(s, assistant_id, body.kb_ids)
        s.flush()
        repo.log_audit(s, user.username, "assistant_update",
                       detail={"assistant": assistant.name})
        return _out(s, assistant)


@router.delete("/assistants/{assistant_id}", status_code=204)
def delete_assistant(assistant_id: uuid.UUID,
                     user: User = Depends(current_user)) -> Response:
    with session_scope() as s:
        if not repo.delete_assistant(s, assistant_id):
            raise HTTPException(404, "assistant not found")
        repo.log_audit(s, user.username, "assistant_delete",
                       detail={"assistant_id": str(assistant_id)})
    return Response(status_code=204)


# ------------------------------------------------------------------ chat

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/assistants/{assistant_id}/chat")
async def assistant_chat(assistant_id: uuid.UUID, body: AssistantChatRequest,
                         user: User = Depends(current_user)) -> StreamingResponse:
    """Chat with one assistant: its KBs are the whole search space, its
    instructions shape the answer, and the thread is saved under it. Same SSE
    contract as the other chat endpoints."""
    from tablerag.query.steps.router import KBRef, LLMRouter

    def prepare() -> dict:
        with session_scope() as s:
            assistant = repo.get_assistant(s, assistant_id)
            if assistant is None:
                raise HTTPException(404, "assistant not found")
            kb_ids = repo.assistant_kb_ids(s, assistant_id)
            if not kb_ids:
                raise HTTPException(
                    400, "this assistant has no knowledge base attached")
            kbs = {kb.id: kb for kb in repo.list_kbs(s)}
            scope = [kbs[k] for k in kb_ids if k in kbs]
            # locale only when unambiguous across the searched KBs
            locales = {(kb.config or {}).get("locale") for kb in scope}
            config = assistant.config or {}
            verify = body.verify
            if verify is None:
                verify = config.get("verify")
            if verify is None and len(scope) == 1:
                verify = (scope[0].config or {}).get("verify")
            # the assistant IS the persona here: it answers "qui es-tu ?"
            identity = assistant.name
            if assistant.description:
                identity = f"{assistant.name} — {assistant.description}"
            stored = repo.get_setting(s, repo.CHAT_INSTRUCTIONS_SETTING) or {}
            extra = "\n\n".join(
                p.strip() for p in (stored.get("text", ""),
                                    assistant.instructions) if p and p.strip())
            history = (repo.get_recent_messages(s, body.session_id)
                       if body.session_id else [])
            return {
                "kb_refs": [KBRef(id=kb.id, name=kb.name,
                                  description=kb.description or "")
                            for kb in scope],
                "kb_ids": [kb.id for kb in scope],
                "locale": locales.pop() if len(locales) == 1 else None,
                "contact": escalation_contact(config),
                "verify": verify, "identity": identity, "extra": extra,
                "history": history,
            }

    cfg = await asyncio.to_thread(prepare)
    kb_refs, kb_ids = cfg["kb_refs"], cfg["kb_ids"]

    async def only_this_assistants_kbs() -> list:
        # the router seam (list_kbs_fn) scopes routing to this assistant, so a
        # question can never be answered from a KB the assistant does not use
        return kb_refs

    async def event_stream():
        ctx = QueryContext(kb_id=kb_ids[0], question=body.question,
                           locale=cfg["locale"], history=cfg["history"],
                           extra_instructions=cfg["extra"],
                           identity=cfg["identity"],
                           escalation_contact=cfg["contact"],
                           # one KB: search it. several: let the router choose
                           # among them (it degrades to all of them, never none)
                           pinned_kb_ids=kb_ids if len(kb_ids) == 1 else None)
        try:
            pipeline = default_pipeline(
                verify=cfg["verify"],
                router=LLMRouter(list_kbs_fn=only_this_assistants_kbs))
            async for kind, payload in pipeline.stream(ctx):
                if kind == "citations":
                    yield _sse({"type": "citations",
                                "citations": [c.model_dump(mode="json")
                                              for c in payload]})
                elif kind == "token":
                    yield _sse({"type": "token", "content": payload})
                elif kind == "caution":
                    # a structured field, never prose in the answer: the model
                    # is not asked to remember to warn anyone
                    yield _sse({"type": "caution",
                                "caution": payload.model_dump(mode="json")})

            def persist() -> tuple[uuid.UUID, uuid.UUID]:
                home = ctx.routed_kb_ids[0] if ctx.routed_kb_ids else kb_ids[0]
                with session_scope() as s:
                    session = repo.get_or_create_session(s, home, body.session_id)
                    repo.link_conversation(s, assistant_id, session.id,
                                           body.question[:TITLE_CHARS])
                    repo.add_message(s, session.id, "user", body.question)
                    repo.log_audit(s, user.username, "query", kb_id=home,
                                   detail={"assistant_id": str(assistant_id),
                                           "question": body.question[:200]})
                    msg = repo.add_message(
                        s, session.id, "assistant", ctx.answer,
                        citations=[c.model_dump(mode="json")
                                   for c in ctx.citations],
                        verification=ctx.verification)
                    return session.id, msg.id

            session_id, message_id = await asyncio.to_thread(persist)
            yield _sse({"type": "done", "session_id": str(session_id),
                        "message_id": str(message_id),
                        "routing": ctx.routing,
                        "search_question": ctx.search_question,
                        "verification": ctx.verification,
                        # printed on the pages the answer used, never read
                        # by the model — a list to click, not a source
                        "see_also": [v.model_dump(mode="json")
                                     for v in ctx.see_also]})
        except Exception:  # noqa: BLE001 — stream errors must reach the client
            logger.exception("assistant chat failed (assistant=%s)", assistant_id)
            yield _sse({"type": "error",
                        "message": "The assistant could not answer this question "
                                   "due to an internal error. Please try again."})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# --------------------------------------------------------- conversations

@router.get("/assistants/{assistant_id}/conversations",
            response_model=list[ConversationOut])
def list_conversations(assistant_id: uuid.UUID) -> list[ConversationOut]:
    with session_scope() as s:
        if repo.get_assistant(s, assistant_id) is None:
            raise HTTPException(404, "assistant not found")
        return [ConversationOut(**c) for c in repo.list_conversations(s, assistant_id)]


@router.get("/conversations/{session_id}/messages")
def conversation_messages(session_id: uuid.UUID) -> dict:
    """Replay a saved thread with everything needed to re-render it."""
    with session_scope() as s:
        link = repo.get_conversation(s, session_id)
        if link is None:
            raise HTTPException(404, "conversation not found")
        return {"session_id": str(session_id), "title": link.title,
                "messages": [{**m, "id": str(m["id"])}
                             for m in repo.get_session_messages(s, session_id)]}


@router.patch("/conversations/{session_id}", response_model=ConversationOut)
def rename_conversation(session_id: uuid.UUID,
                        body: ConversationRename) -> ConversationOut:
    with session_scope() as s:
        link = repo.rename_conversation(s, session_id, body.title.strip())
        if link is None:
            raise HTTPException(404, "conversation not found")
        return ConversationOut(session_id=link.session_id, title=link.title,
                               created_at=link.created_at,
                               updated_at=link.updated_at)


@router.delete("/conversations/{session_id}", status_code=204)
def delete_conversation(session_id: uuid.UUID) -> Response:
    with session_scope() as s:
        if not repo.delete_conversation(s, session_id):
            raise HTTPException(404, "conversation not found")
    return Response(status_code=204)
