import asyncio
import uuid

from fastapi import APIRouter, HTTPException

from tablerag.core.schemas import KBCreate, KBOut, KBUpdate
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

router = APIRouter(prefix="/api/kbs", tags=["knowledge-bases"])

_LOCALE_LANGUAGE = {"fr": "French", "de": "German", "en": "English",
                    "es": "Spanish", "it": "Italian", "pt": "Portuguese"}


def build_describe_prompt(sample: str, locale: str | None) -> str:
    """Ask for a one/two-sentence description of what a KB covers — the text
    the router reads to decide when to search it, so it must name subjects."""
    lang = _LOCALE_LANGUAGE.get(locale or "", "the documents' language")
    return (
        "Below are excerpts from the documents in one knowledge base.\n"
        "In ONE or TWO sentences, describe what subjects this knowledge base "
        "covers, so a router can decide when to search it. Name the topics "
        "concretely; do not summarize individual documents or add preamble.\n"
        f"Write the description in {lang}.\n\n"
        f"{sample}\n\nDescription:")


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


@router.post("/{kb_id}/suggest-description")
async def suggest_description(kb_id: uuid.UUID) -> dict:
    """Draft a KB description from its first documents (SPEC Phase 5). The user
    reviews and saves it via PATCH — a good description is what the router
    reads, so this exists to stop empty/weak descriptions blinding the router."""
    def load() -> tuple[str, str | None]:
        with session_scope() as s:
            kb = repo.get_kb(s, kb_id)
            if kb is None:
                raise HTTPException(404, "knowledge base not found")
            return (repo.content_sample(s, kb_id),
                    (kb.config or {}).get("locale"))

    sample, locale = await asyncio.to_thread(load)
    if not sample:
        raise HTTPException(400, "no document content yet — upload and let at "
                                 "least one document finish processing first")

    from tablerag.models.base import Msg
    from tablerag.models.registry import get_provider

    chat = get_provider("chat")
    parts: list[str] = []
    async for token in chat.chat(
            [Msg(role="user", content=build_describe_prompt(sample, locale))],
            stream=True, temperature=0.0, options={"temperature": 0.0}):
        parts.append(token)
    return {"description": "".join(parts).strip()}


@router.get("/{kb_id}/needs-review")
def needs_review(kb_id: uuid.UUID) -> dict:
    """The KB's review queue: tables/elements the parser flagged as unsure.
    Surfaced at KB level so a non-engineer is nudged to check them instead of
    hunting per document (SPEC Phase 5)."""
    with session_scope() as s:
        if repo.get_kb(s, kb_id) is None:
            raise HTTPException(404, "knowledge base not found")
        items = repo.needs_review_elements(s, kb_id)
    return {"count": len(items),
            "items": [{**it, "element_id": str(it["element_id"]),
                       "doc_id": str(it["doc_id"])} for it in items]}


@router.get("/{kb_id}", response_model=KBOut)
def get_kb(kb_id: uuid.UUID) -> KBOut:
    with session_scope() as s:
        kb = repo.get_kb(s, kb_id)
        if kb is None:
            raise HTTPException(404, "knowledge base not found")
        return KBOut.model_validate(kb, from_attributes=True)
