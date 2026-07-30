import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from tablerag.core.auth import User, current_user
from tablerag.core.queue import TASK_PROCESS_DOCUMENT, celery_app
from tablerag.core.schemas import (
    BoilerplateCandidate,
    BoilerplateExcludeRequest,
    BulkDeleteRequest,
    DocumentOut,
)
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope
from tablerag.ingestion.convert import (
    SUPPORTED_SUFFIXES,
    content_type_for,
    is_supported,
)
from tablerag.storage.object_store import (
    doc_prefix,
    doc_source_key,
    get_object_store,
    page_image_key,
)
from tablerag.storage.qdrant import get_vector_store

router = APIRouter(prefix="/api", tags=["documents"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@router.post("/kbs/{kb_id}/documents", response_model=DocumentOut, status_code=202)
async def upload_document(kb_id: uuid.UUID, file: UploadFile,
                          user: User = Depends(current_user)) -> DocumentOut:
    filename = file.filename or "document.pdf"
    if not is_supported(filename):
        raise HTTPException(
            400, "Unsupported file type. Accepted: "
                 f"{', '.join(sorted(SUPPORTED_SUFFIXES))}.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the 200 MB upload limit.")

    doc_id = uuid.uuid4()
    # stored exactly as uploaded (a .pptx stays a .pptx); an Office document is
    # converted to PDF by the worker and cached alongside it
    key = doc_source_key(kb_id, doc_id, filename)
    with session_scope() as s:
        if repo.get_kb(s, kb_id) is None:
            raise HTTPException(404, "knowledge base not found")
        get_object_store().put(key, data, content_type_for(filename))
        doc = repo.create_document(s, kb_id, filename, key, doc_id=doc_id)
        repo.log_audit(s, user.username, "upload", kb_id=kb_id, doc_id=doc_id,
                       detail={"filename": filename, "bytes": len(data)})
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


IN_FLIGHT = ("queued", "parsing", "indexing")


def _requeue_document(doc_id: uuid.UUID, kb_id: uuid.UUID, actor: str) -> None:
    """Clear the error, drop stale element crops and re-enqueue. The task is
    idempotent — it wipes the document's previous elements and vectors before
    re-parsing — so the original file and page renders are kept."""
    # element crops are keyed by the OLD element ids, so they would be orphaned;
    # original.pdf, converted.pdf and pages/ are left untouched
    get_object_store().delete_prefix(f"{doc_prefix(kb_id, doc_id)}/elements")
    with session_scope() as s:
        repo.set_document_status(s, doc_id, "queued")  # also clears the error
        repo.log_audit(s, actor, "reprocess", kb_id=kb_id, doc_id=doc_id)
    celery_app.send_task(TASK_PROCESS_DOCUMENT, args=[str(doc_id)])


@router.post("/documents/{doc_id}/reprocess", response_model=DocumentOut)
def reprocess_document(doc_id: uuid.UUID,
                       user: User = Depends(current_user)) -> DocumentOut:
    """Re-run ingestion for one document (after a transient failure, or to pick
    up a parsing change that only applies to newly ingested pages)."""
    with session_scope() as s:
        doc = repo.get_document(s, doc_id)
        if doc is None:
            raise HTTPException(404, "document not found")
        if doc.status in IN_FLIGHT:
            raise HTTPException(409, "document is already being processed")
        kb_id = doc.kb_id
    _requeue_document(doc_id, kb_id, user.username)
    with session_scope() as s:
        out = DocumentOut.model_validate(repo.get_document(s, doc_id),
                                         from_attributes=True)
    return out


def _purge_document(doc_id: uuid.UUID) -> bool:
    """Remove one document from all three stores. Returns False if unknown.
    External stores first: if the Postgres delete later fails, the doc is
    still gone from retrieval and disk (no orphaned vectors serving stale
    answers)."""
    with session_scope() as s:
        doc = repo.get_document(s, doc_id)
        if doc is None:
            return False
        kb_id = doc.kb_id
    get_vector_store().delete_doc(doc_id)
    get_object_store().delete_prefix(doc_prefix(kb_id, doc_id))
    with session_scope() as s:
        repo.delete_document(s, doc_id)
    return True


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: uuid.UUID) -> Response:
    """Remove a document from all three stores (vectors, files, Postgres)."""
    if not _purge_document(doc_id):
        raise HTTPException(404, "document not found")
    return Response(status_code=204)


@router.post("/kbs/{kb_id}/documents/bulk-delete")
def bulk_delete_documents(kb_id: uuid.UUID, body: BulkDeleteRequest) -> dict:
    """Delete several documents at once (select-many / delete-all in the UI).
    Only documents that belong to this KB are touched.

    Batched, not per-document: a single MatchAny vector delete per collection
    and one Postgres delete, instead of N×(3 Qdrant round-trips) in one request
    — deleting dozens of documents used to run long enough for the browser to
    abort the fetch ('NetworkError'). External stores go first so a later
    Postgres failure can't leave orphaned vectors serving stale answers."""
    with session_scope() as s:
        if repo.get_kb(s, kb_id) is None:
            raise HTTPException(404, "knowledge base not found")
        owned = {d.id for d in repo.list_documents(s, kb_id)}
    targets = [doc_id for doc_id in body.doc_ids if doc_id in owned]
    if not targets:
        return {"deleted": 0}

    get_vector_store().delete_docs(targets)
    store = get_object_store()
    for doc_id in targets:
        store.delete_prefix(doc_prefix(kb_id, doc_id))
    with session_scope() as s:
        deleted = repo.delete_documents(s, targets)
    return {"deleted": deleted}


@router.post("/kbs/{kb_id}/documents/bulk-reprocess")
def bulk_reprocess_documents(kb_id: uuid.UUID, body: BulkDeleteRequest,
                             user: User = Depends(current_user)) -> dict:
    """Re-run ingestion for several documents at once (select-many / select-all
    in the UI) — after a batch of transient failures, or to pick up a parsing
    change that only applies to newly ingested pages.

    Only documents belonging to this KB are touched, and one already in flight
    is skipped rather than enqueued twice. They are queued, not run here: the
    worker takes them one at a time, which is what keeps a large batch from
    overwhelming the box the way a mass upload once did."""
    with session_scope() as s:
        if repo.get_kb(s, kb_id) is None:
            raise HTTPException(404, "knowledge base not found")
        owned = {d.id: d.status for d in repo.list_documents(s, kb_id)}
    wanted = [doc_id for doc_id in body.doc_ids if doc_id in owned]
    targets = [doc_id for doc_id in wanted if owned[doc_id] not in IN_FLIGHT]
    for doc_id in targets:
        _requeue_document(doc_id, kb_id, user.username)
    return {"queued": len(targets), "skipped": len(wanted) - len(targets)}


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


@router.post("/documents/{doc_id}/boilerplate-scan",
             response_model=list[BoilerplateCandidate])
def scan_boilerplate(doc_id: uuid.UUID,
                     _user: User = Depends(current_user),
                     ) -> list[BoilerplateCandidate]:
    """Read-only: find running headers/footers/page numbers among this
    document's TEXT elements (repetition across pages at a consistent margin).
    Changes nothing — the caller reviews and confirms before excluding."""
    from tablerag.ingestion.boilerplate import BoilerElement, detect_boilerplate

    with session_scope() as s:
        if repo.get_document(s, doc_id) is None:
            raise HTTPException(404, "document not found")
        rows = repo.get_text_elements(s, doc_id)
    elements = [
        BoilerElement(id=str(r["id"]), page=r["page"],
                      bbox=tuple((r["bbox"] or [0, 0, 0, 0])[:4]), text=r["text"])
        for r in rows
    ]
    return [BoilerplateCandidate(element_id=uuid.UUID(c.element_id), page=c.page,
                                 reason=c.reason, text=c.text)
            for c in detect_boilerplate(elements)]


@router.post("/documents/{doc_id}/boilerplate-exclude")
def exclude_boilerplate(doc_id: uuid.UUID, body: BoilerplateExcludeRequest,
                        user: User = Depends(current_user)) -> dict:
    """Exclude the confirmed elements from retrieval — same mechanism as the
    review flow's 'mark unusable': the element and its image stay, its vectors
    are removed so it can no longer pollute answers."""
    from tablerag.storage.orm import Element

    with session_scope() as s:
        if repo.get_document(s, doc_id) is None:
            raise HTTPException(404, "document not found")
        excluded: list[uuid.UUID] = []
        for eid in body.element_ids:
            el = s.get(Element, eid)
            if el is None or el.doc_id != doc_id:
                continue  # only this document's own elements
            repo.mark_element_unusable(s, eid)
            excluded.append(eid)
        repo.log_audit(s, user.username, "boilerplate_exclude", doc_id=doc_id,
                       detail={"count": len(excluded)})
    store = get_vector_store()
    for eid in excluded:
        store.delete_element(eid)
    return {"excluded": len(excluded)}


@router.get("/documents/{doc_id}/original")
def get_original_document(doc_id: uuid.UUID) -> Response:
    """Serve the original source PDF so the parse can be compared against it at
    full fidelity (principle #3). It is already stored at upload time."""
    with session_scope() as s:
        doc = repo.get_document(s, doc_id)
        if doc is None:
            raise HTTPException(404, "document not found")
        key, filename = doc.file_path, doc.filename
    store = get_object_store()
    if not store.exists(key):
        raise HTTPException(404, "original document not found")
    # inline so the browser previews a PDF; an Office file keeps its own type so
    # it downloads as the .pptx/.docx it really is. strip anything that could
    # break the header, keep an ascii fallback name
    safe = "".join(c for c in filename if c.isalnum() or c in " ._-").strip()
    return Response(
        content=store.get(key), media_type=content_type_for(filename),
        headers={"Content-Disposition":
                 f'inline; filename="{safe or "document.pdf"}"'})
