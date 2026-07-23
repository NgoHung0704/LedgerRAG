"""Who am I + the audit trail — the account-level surface (SPEC Phase 5)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from tablerag.core.auth import User, current_user, require_admin
from tablerag.core.schemas import ChatInstructions
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"username": user.username, "email": user.email,
            "is_admin": user.is_admin}


@router.get("/settings/chat-instructions", response_model=ChatInstructions)
def get_chat_instructions(_user: User = Depends(current_user)) -> ChatInstructions:
    """Global extra guidance appended to every chat system prompt. Readable by
    any user (the Settings UI shows it); only admins can change it."""
    with session_scope() as s:
        stored = repo.get_setting(s, repo.CHAT_INSTRUCTIONS_SETTING) or {}
    return ChatInstructions(text=stored.get("text", ""))


@router.put("/settings/chat-instructions", response_model=ChatInstructions)
def put_chat_instructions(body: ChatInstructions,
                          admin: User = Depends(require_admin)) -> ChatInstructions:
    text = body.text.strip()
    with session_scope() as s:
        repo.set_setting(s, repo.CHAT_INSTRUCTIONS_SETTING, {"text": text})
        # audit the change, never the full text (may be long / sensitive)
        repo.log_audit(s, admin.username, "model_config",
                       detail={"setting": "chat_instructions", "chars": len(text)})
    return ChatInstructions(text=text)


@router.get("/audit")
async def audit(limit: int = 200, _admin=Depends(require_admin)) -> dict:
    """GDPR accountability trail (admin only): who uploaded / queried / changed
    model config, most recent first."""
    def load() -> list[dict]:
        with session_scope() as s:
            return [{"actor": e.actor, "action": e.action,
                     "kb_id": str(e.kb_id) if e.kb_id else None,
                     "doc_id": str(e.doc_id) if e.doc_id else None,
                     "detail": e.detail,
                     "created_at": e.created_at.isoformat()}
                    for e in repo.recent_audit(s, min(limit, 1000))]

    return {"events": await asyncio.to_thread(load)}
