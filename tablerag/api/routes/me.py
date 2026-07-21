"""Who am I + the audit trail — the account-level surface (SPEC Phase 5)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from tablerag.core.auth import User, current_user, require_admin
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"username": user.username, "email": user.email,
            "is_admin": user.is_admin}


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
