import uuid

from fastapi import APIRouter, HTTPException

from tablerag.core.schemas import KBCreate, KBOut, KBUpdate
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

router = APIRouter(prefix="/api/kbs", tags=["knowledge-bases"])


@router.post("", response_model=KBOut, status_code=201)
def create_kb(body: KBCreate) -> KBOut:
    config: dict = {"verify": body.verify}
    if body.locale:
        config["locale"] = body.locale
    with session_scope() as s:
        kb = repo.create_kb(s, name=body.name, description=body.description,
                            config=config)
        return KBOut.model_validate(kb, from_attributes=True)


@router.get("", response_model=list[KBOut])
def list_kbs() -> list[KBOut]:
    with session_scope() as s:
        return [KBOut.model_validate(kb, from_attributes=True)
                for kb in repo.list_kbs(s)]


@router.patch("/{kb_id}", response_model=KBOut)
def update_kb(kb_id: uuid.UUID, body: KBUpdate) -> KBOut:
    """Change a KB's settings after creation (locale / verification / naming)."""
    with session_scope() as s:
        kb = repo.get_kb(s, kb_id)
        if kb is None:
            raise HTTPException(404, "knowledge base not found")
        if body.name is not None:
            kb.name = body.name
        if body.description is not None:
            kb.description = body.description
        # JSONB mutation tracking: rebind a new dict, never mutate in place
        config = dict(kb.config or {})
        if body.locale is not None:
            config["locale"] = body.locale
        if body.verify is not None:
            config["verify"] = body.verify
        kb.config = config
        s.flush()
        return KBOut.model_validate(kb, from_attributes=True)


@router.get("/{kb_id}", response_model=KBOut)
def get_kb(kb_id: uuid.UUID) -> KBOut:
    with session_scope() as s:
        kb = repo.get_kb(s, kb_id)
        if kb is None:
            raise HTTPException(404, "knowledge base not found")
        return KBOut.model_validate(kb, from_attributes=True)
