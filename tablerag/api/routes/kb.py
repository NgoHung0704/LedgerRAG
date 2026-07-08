import uuid

from fastapi import APIRouter, HTTPException

from tablerag.core.schemas import KBCreate, KBOut
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

router = APIRouter(prefix="/api/kbs", tags=["knowledge-bases"])


@router.post("", response_model=KBOut, status_code=201)
def create_kb(body: KBCreate) -> KBOut:
    config = {"locale": body.locale} if body.locale else {}
    with session_scope() as s:
        kb = repo.create_kb(s, name=body.name, description=body.description,
                            config=config)
        return KBOut.model_validate(kb, from_attributes=True)


@router.get("", response_model=list[KBOut])
def list_kbs() -> list[KBOut]:
    with session_scope() as s:
        return [KBOut.model_validate(kb, from_attributes=True)
                for kb in repo.list_kbs(s)]


@router.get("/{kb_id}", response_model=KBOut)
def get_kb(kb_id: uuid.UUID) -> KBOut:
    with session_scope() as s:
        kb = repo.get_kb(s, kb_id)
        if kb is None:
            raise HTTPException(404, "knowledge base not found")
        return KBOut.model_validate(kb, from_attributes=True)
