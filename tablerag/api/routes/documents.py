import uuid

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response

from tablerag.core.queue import TASK_PROCESS_DOCUMENT, celery_app
from tablerag.core.schemas import DocumentOut
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope
from tablerag.storage.object_store import (
    doc_pdf_key,
    doc_prefix,
    get_object_store,
    page_image_key,
)
from tablerag.storage.qdrant import get_vector_store

router = APIRouter(prefix="/api", tags=["documents"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@router.post("/kbs/{kb_id}/documents", response_model=DocumentOut, status_code=202)
async def upload_document(kb_id: uuid.UUID, file: UploadFile) -> DocumentOut:
    filename = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the 200 MB upload limit.")

    doc_id = uuid.uuid4()
    key = doc_pdf_key(kb_id, doc_id)
    with session_scope() as s:
        if repo.get_kb(s, kb_id) is None:
            raise HTTPException(404, "knowledge base not found")
        get_object_store().put(key, data, "application/pdf")
        doc = repo.create_document(s, kb_id, filename, key, doc_id=doc_id)
        out = DocumentOut.model_validate(doc, from_attributes=True)

    # enqueue by task name — the API never imports the ingestion package
    celery_app.send_task(TASK_PROCESS_DOCUMENT, args=[str(doc_id)])
    return out


@router.get("/kbs/{kb_id}/documents", response_model=list[DocumentOut])
def list_documents(kb_id: uuid.UUID) -> list[DocumentOut]:
    with session_scope() as s:
        if repo.get_kb(s, kb_id) is None:
            raise HTTPException(404, "knowledge base not found")
        return [DocumentOut.model_validate(d, from_attributes=True)
                for d in repo.list_documents(s, kb_id)]


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: uuid.UUID) -> DocumentOut:
    with session_scope() as s:
        doc = repo.get_document(s, doc_id)
        if doc is None:
            raise HTTPException(404, "document not found")
        return DocumentOut.model_validate(doc, from_attributes=True)


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: uuid.UUID) -> Response:
    """Remove a document from all three stores: vectors (Qdrant), files
    (object store), then Postgres rows (elements/chunks/records cascade)."""
    with session_scope() as s:
        doc = repo.get_document(s, doc_id)
        if doc is None:
            raise HTTPException(404, "document not found")
        kb_id = doc.kb_id
    # external stores first: if Postgres delete later fails, the doc is still
    # gone from retrieval and disk (no orphaned vectors serving stale answers)
    get_vector_store().delete_doc(doc_id)
    get_object_store().delete_prefix(doc_prefix(kb_id, doc_id))
    with session_scope() as s:
        repo.delete_document(s, doc_id)
    return Response(status_code=204)


@router.get("/documents/{doc_id}/elements")
def get_document_elements(doc_id: uuid.UUID) -> dict:
    """Inspector: everything ingestion produced for this document — per
    element, with the three table representations and crop-image links."""
    with session_scope() as s:
        doc = repo.get_document(s, doc_id)
        if doc is None:
            raise HTTPException(404, "document not found")
        elements = repo.get_document_view(s, doc_id)
        document = DocumentOut.model_validate(doc, from_attributes=True)
    for element in elements:
        element["crop_url"] = f"/api/elements/{element['id']}/image"
    return {"document": document, "elements": elements}


@router.get("/documents/{doc_id}/pages/{page}/image")
def get_page_image(doc_id: uuid.UUID, page: int) -> Response:
    """Serve the stored page render — the citation click-through target
    (principle #3: answer -> source page image must always be reachable)."""
    with session_scope() as s:
        doc = repo.get_document(s, doc_id)
        if doc is None:
            raise HTTPException(404, "document not found")
        kb_id = doc.kb_id
    key = page_image_key(kb_id, doc_id, page)
    store = get_object_store()
    if not store.exists(key):
        raise HTTPException(404, "page image not found")
    return Response(content=store.get(key), media_type="image/png")
