"""Element detail + crop image — the citation click-through target
(principle #3: answer -> element -> crop image -> PDF page, always)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope
from tablerag.storage.object_store import get_object_store

router = APIRouter(prefix="/api/elements", tags=["elements"])


@router.get("/{element_id}")
def get_element(element_id: uuid.UUID) -> dict:
    with session_scope() as s:
        detail = repo.get_element_detail(s, element_id)
    if detail is None:
        raise HTTPException(404, "element not found")
    detail["crop_url"] = f"/api/elements/{element_id}/image"
    return detail


@router.get("/{element_id}/image")
def get_element_image(element_id: uuid.UUID) -> Response:
    with session_scope() as s:
        from tablerag.storage.orm import Element

        element = s.get(Element, element_id)
        if element is None:
            raise HTTPException(404, "element not found")
        key = element.crop_image_path
    store = get_object_store()
    if not store.exists(key):
        raise HTTPException(404, "crop image not found")
    return Response(content=store.get(key), media_type="image/png")
