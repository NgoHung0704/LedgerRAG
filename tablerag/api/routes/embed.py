"""One assistant, served to another application by token.

This is the only prefix `auth_middleware` lets through without an identity, so
every route here resolves the token itself and answers 404 when it does not
match. 404 rather than 403 on purpose: a 403 confirms there is an assistant
there and you merely lack permission.

Nothing else is reachable with a token — not the assistant list, not the
knowledge bases, not upload, not settings. The chat route takes no assistant id,
so a valid token cannot be aimed at a different assistant.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from tablerag.api.routes.assistants import assistant_chat_response
from tablerag.core.schemas import AssistantChatRequest, EmbedFace
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

router = APIRouter(prefix="/api/embed", tags=["embed"])


def _resolve(token: str) -> tuple[uuid.UUID, str]:
    """The assistant this token stands for, as (id, name). 404 otherwise."""
    with session_scope() as s:
        assistant = repo.get_assistant_by_embed_token(s, token)
        if assistant is None:
            raise HTTPException(404, "not found")
        return assistant.id, assistant.name


@router.get("/{token}", response_model=EmbedFace)
def embed_face(token: str) -> EmbedFace:
    with session_scope() as s:
        assistant = repo.get_assistant_by_embed_token(s, token)
        if assistant is None:
            raise HTTPException(404, "not found")
        config = assistant.config or {}
        return EmbedFace(name=assistant.name,
                         description=assistant.description or "",
                         opening_message=config.get("opening_message", ""))


@router.post("/{token}/chat")
async def embed_chat(token: str,
                     body: AssistantChatRequest) -> StreamingResponse:
    """The same pipeline the signed-in assistant chat runs.

    The audit actor names the embed rather than a person, because there is no
    person: `embed:<assistant name>` is what /audit shows.
    """
    assistant_id, name = _resolve(token)
    return await assistant_chat_response(assistant_id, body, f"embed:{name}")
