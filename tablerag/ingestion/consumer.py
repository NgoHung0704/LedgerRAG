"""Paperless-style consume folder: drop PDFs into consume/<KB name>/ and they
are auto-ingested into that knowledge base (created if it doesn't exist).

A standalone polling loop (its own compose service), deliberately simple: no
Celery Beat, no filesystem-watch dependency. It reuses the exact upload path the
API uses — store the PDF in the object store, create the document row, enqueue
process_document by name — so ingestion↔serving isolation (principle #1) holds:
the consumer never imports the ingestion task implementation.

Rules:
  - A file must live in a subfolder named after the target KB
    (subfolder = KB name). A PDF in the root is ignored.
  - A file is only picked up once it has been unmodified for
    `consume_stability_secs`, so a half-copied upload is never grabbed.
  - A file is *claimed* (moved to `<root>/.processed/…`) BEFORE it is ingested,
    so it can never be ingested twice; a failed ingest leaves the file there for
    inspection rather than retrying into a duplicate.

Enable by mounting a directory and setting LEDGERRAG_CONSUME_DIR (see
docker-compose). Empty (default) = the service idles.
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from pathlib import Path

from tablerag.core.queue import TASK_PROCESS_DOCUMENT, celery_app
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

logger = logging.getLogger(__name__)

ARCHIVE_DIRNAME = ".processed"


# --------------------------------------------------------------- pure helpers

def discover_pdfs(root: Path) -> list[Path]:
    """Every candidate PDF under `root`, excluding the archive dir and hidden
    files. Returned in a stable order."""
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if ARCHIVE_DIRNAME in rel.parts:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        if path.suffix.lower() != ".pdf":
            continue
        out.append(path)
    return out


def kb_name_from_path(root: Path, pdf: Path) -> str | None:
    """The KB a file maps to: the first path component under `root`. None when
    the file sits directly in the root (no KB subfolder)."""
    rel = pdf.relative_to(root)
    return rel.parts[0] if len(rel.parts) >= 2 else None


def is_stable(path: Path, min_age_secs: float, now: float | None = None) -> bool:
    """True when the file hasn't been modified for at least `min_age_secs` — a
    guard against grabbing a file mid-copy."""
    now = time.time() if now is None else now
    try:
        return (now - path.stat().st_mtime) >= min_age_secs
    except OSError:
        return False


def archive_destination(root: Path, pdf: Path) -> Path:
    """Where an ingested file is moved, preserving its KB subfolder under the
    archive dir; a name clash gets a numeric suffix rather than clobbering."""
    dest = root / ARCHIVE_DIRNAME / pdf.relative_to(root)
    if not dest.exists():
        return dest
    stem, suffix, n = dest.stem, dest.suffix, 1
    while True:
        candidate = dest.with_name(f"{stem}_{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1


# --------------------------------------------------------------- ingest

def ingest_file(path: Path, kb_name: str, filename: str | None = None) -> uuid.UUID:
    """Store the PDF at `path`, create its document row under KB `kb_name`
    (created if needed) using `filename` (defaults to path.name) as the display
    name, and enqueue processing. Mirrors the API's upload_document."""
    from tablerag.storage.object_store import doc_pdf_key, get_object_store

    data = path.read_bytes()
    if not data:
        raise ValueError("empty file")
    name = filename or path.name
    doc_id = uuid.uuid4()
    with session_scope() as s:
        kb = repo.get_or_create_kb_by_name(s, kb_name)
        key = doc_pdf_key(kb.id, doc_id)
        get_object_store().put(key, data, "application/pdf")
        repo.create_document(s, kb.id, name, key, doc_id=doc_id)
        repo.log_audit(s, "consumer", "upload", kb_id=kb.id, doc_id=doc_id,
                       detail={"filename": name, "source": "consume-folder"})
    # enqueue only after the row is committed, so the worker never races a
    # not-yet-visible document (enqueue by name — no ingestion import).
    celery_app.send_task(TASK_PROCESS_DOCUMENT, args=[str(doc_id)])
    return doc_id


def _claim(root: Path, pdf: Path) -> Path | None:
    """Move a file into the archive to claim it before ingesting — so a later
    failure can't leave it to be re-ingested into a duplicate. None if the move
    fails (another poll/process took it, or a permission problem)."""
    dest = archive_destination(root, pdf)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        pdf.rename(dest)
    except OSError:
        try:
            shutil.move(str(pdf), str(dest))  # cross-device fallback
        except OSError:
            logger.exception("consume: could not claim %s", pdf)
            return None
    return dest


def process_once(root: Path, stability_secs: float,
                 now: float | None = None) -> list[uuid.UUID]:
    """One scan: claim then ingest every stable, correctly-placed PDF. Returns
    the doc ids enqueued this pass. Never raises on a single bad file."""
    enqueued: list[uuid.UUID] = []
    for pdf in discover_pdfs(root):
        kb_name = kb_name_from_path(root, pdf)
        if kb_name is None:
            logger.debug("consume: ignoring root-level %s (needs a KB subfolder)",
                         pdf.name)
            continue
        if not is_stable(pdf, stability_secs, now):
            continue  # still being written — try again next tick
        original_name = pdf.name
        claimed = _claim(root, pdf)
        if claimed is None:
            continue
        try:
            doc_id = ingest_file(claimed, kb_name, filename=original_name)
        except Exception:  # noqa: BLE001 — one bad file must not stall the folder
            logger.exception("consume: ingest failed for %s (kept at %s)",
                             original_name, claimed)
            continue
        logger.info("consume: ingested %s -> KB %r (doc %s)", original_name,
                    kb_name, doc_id)
        enqueued.append(doc_id)
    return enqueued


def run(root: Path, interval_secs: float, stability_secs: float) -> None:
    logger.info("consume: watching %s every %.0fs (stability %.0fs)", root,
                interval_secs, stability_secs)
    while True:
        try:
            process_once(root, stability_secs)
        except Exception:  # noqa: BLE001 — a bad poll must not kill the loop
            logger.exception("consume: poll failed")
        time.sleep(interval_secs)


def main() -> None:
    from tablerag.core.config import get_settings
    from tablerag.core.logging import setup_logging

    setup_logging()
    settings = get_settings()
    if not settings.consume_dir:
        logger.info("consume: LEDGERRAG_CONSUME_DIR not set — consumer idle")
        while True:  # stay up (compose service) rather than crash-loop
            time.sleep(3600)
    root = Path(settings.consume_dir)
    root.mkdir(parents=True, exist_ok=True)
    run(root, settings.consume_interval, settings.consume_stability_secs)


if __name__ == "__main__":
    main()
