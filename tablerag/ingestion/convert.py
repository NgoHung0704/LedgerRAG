"""Office documents -> PDF, so the whole measured pipeline applies unchanged.

A .pptx/.docx/.xlsx is converted with LibreOffice before ingestion, then parsed
exactly like any PDF. That is deliberate: principle #3 requires every element to
trace back to a stored image of where it came from (`element.crop_image_path` is
NOT NULL), and a native XML reader produces no page rendering. Going through PDF
keeps page renders, table detection, grid hints, confidence, cross-page merge,
crops and citations — all of it already measured — and LibreOffice emits a real
text layer, so office files land on the high-quality text-layer path rather than
the VLM scan path.

Conversion failures are PERMANENT (a file LibreOffice cannot read will not read
differently on a retry), so they surface honestly on the document instead of
being retried like a transient infrastructure error.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# what ingestion accepts. PDF is here so callers can validate uploads against one
# list; it is the only one that never goes near LibreOffice.
SUPPORTED_SUFFIXES = frozenset({
    ".pdf",
    ".pptx", ".ppt",
    ".docx", ".doc",
    ".xlsx", ".xls",
})

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}

SOFFICE_BINARIES = ("soffice", "libreoffice")


class ConversionError(Exception):
    """The file could not be turned into a PDF — reported on the document."""


def suffix_of(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def is_supported(filename: str) -> bool:
    return suffix_of(filename) in SUPPORTED_SUFFIXES


def needs_conversion(filename: str) -> bool:
    """PDFs pass straight through: the existing path keeps its exact behaviour,
    with no subprocess and no new way to fail."""
    return is_supported(filename) and suffix_of(filename) != ".pdf"


def content_type_for(filename: str) -> str:
    return CONTENT_TYPES.get(suffix_of(filename), "application/octet-stream")


def _find_soffice() -> str:
    for name in SOFFICE_BINARIES:
        path = shutil.which(name)
        if path:
            return path
    raise ConversionError(
        "LibreOffice is not installed in the worker image, so Office documents "
        "cannot be converted. Rebuild the image (it installs libreoffice-impress"
        ", -writer and -calc) or upload a PDF instead.")


def to_pdf(data: bytes, filename: str, timeout: int = 180) -> bytes:
    """Convert an Office document to PDF bytes. Raises ConversionError."""
    suffix = suffix_of(filename)
    if suffix == ".pdf":
        return data
    if suffix not in SUPPORTED_SUFFIXES:
        raise ConversionError(
            f"{suffix or 'This file type'} is not supported. Upload one of: "
            f"{', '.join(sorted(SUPPORTED_SUFFIXES))}.")

    soffice = _find_soffice()
    with tempfile.TemporaryDirectory(prefix="ledgerrag-convert-") as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / f"input{suffix}"
        source.write_bytes(data)
        outdir = tmp_path / "out"
        outdir.mkdir()
        # a PRIVATE user profile per conversion: LibreOffice serialises on the
        # shared default profile, so two concurrent conversions would hang or
        # silently produce nothing
        profile = (tmp_path / "profile").as_uri()
        cmd = [soffice, "--headless", "--norestore", "--nolockcheck",
               f"-env:UserInstallation={profile}",
               "--convert-to", "pdf", "--outdir", str(outdir), str(source)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout,
                                  check=False)
        except subprocess.TimeoutExpired as e:
            raise ConversionError(
                f"Converting this document timed out after {timeout}s. It may be "
                "very large or malformed.") from e
        except OSError as e:  # binary vanished between which() and run()
            raise ConversionError(f"LibreOffice could not be started: {e}") from e

        produced = sorted(outdir.glob("*.pdf"))
        if not produced:
            detail = (proc.stderr or proc.stdout or b"").decode(
                "utf-8", "replace").strip()
            raise ConversionError(
                "LibreOffice produced no PDF for this document"
                + (f": {detail[:300]}" if detail else
                   f" (exit code {proc.returncode})."))
        pdf = produced[0].read_bytes()
    if not pdf:
        raise ConversionError("The converted PDF was empty.")
    logger.info("converted %s (%d bytes) -> pdf (%d bytes)",
                filename, len(data), len(pdf))
    return pdf
