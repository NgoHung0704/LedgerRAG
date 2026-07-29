"""Office -> PDF conversion: the plumbing, without needing LibreOffice.

Two properties matter. A PDF must take the old path byte-for-byte (no
subprocess, no new way to fail), and every conversion failure must surface as a
ConversionError carrying a message an operator can act on — the ingest task
reports those verbatim on the document instead of retrying them.
"""

import subprocess
from pathlib import Path

import pytest

from tablerag.ingestion import convert
from tablerag.ingestion.convert import (
    ConversionError,
    content_type_for,
    is_supported,
    needs_conversion,
    to_pdf,
)
from tablerag.storage.object_store import doc_converted_pdf_key, doc_source_key


# --- what we accept ---------------------------------------------------------

@pytest.mark.parametrize("name,ok", [
    ("accord.pdf", True),
    ("Presentation RH.pptx", True),
    ("reglement.docx", True),
    ("bareme.xlsx", True),
    ("old.ppt", True),
    ("UPPER.PDF", True),
    ("archive.zip", False),
    ("script.exe", False),
    ("noextension", False),
    ("", False),
])
def test_is_supported(name, ok):
    assert is_supported(name) is ok


def test_only_office_files_need_conversion():
    assert needs_conversion("deck.pptx") is True
    assert needs_conversion("notes.docx") is True
    assert needs_conversion("accord.pdf") is False   # the untouched path
    assert needs_conversion("archive.zip") is False  # unsupported, not converted


def test_content_types():
    assert content_type_for("a.pdf") == "application/pdf"
    assert "presentationml" in content_type_for("a.pptx")
    assert "wordprocessingml" in content_type_for("a.docx")
    assert content_type_for("a.weird") == "application/octet-stream"


# --- the PDF path is untouched ---------------------------------------------

def test_pdf_passes_through_without_running_anything(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: pytest.fail("a PDF must not be converted"))
    data = b"%PDF-1.7 ..."
    assert to_pdf(data, "accord.pdf") is data


def test_unsupported_type_is_refused_before_any_work(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(ConversionError, match="not supported"):
        to_pdf(b"x", "archive.zip")


# --- conversion, with a stubbed LibreOffice --------------------------------

def _fake_soffice(monkeypatch, *, writes=b"%PDF-1.4 converted",
                  returncode=0, stderr=b"", raises=None):
    """Stand in for `soffice`: writes the PDF the real one would produce."""
    monkeypatch.setattr(convert.shutil, "which", lambda name: "/usr/bin/soffice")

    def run(cmd, capture_output=True, timeout=None, check=False):
        if raises is not None:
            raise raises
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        if writes:
            (outdir / "input.pdf").write_bytes(writes)
        return subprocess.CompletedProcess(cmd, returncode, b"", stderr)

    monkeypatch.setattr(convert.subprocess, "run", run)


def test_successful_conversion_returns_the_pdf(monkeypatch):
    _fake_soffice(monkeypatch)
    assert to_pdf(b"pptx-bytes", "deck.pptx") == b"%PDF-1.4 converted"


def test_each_conversion_gets_a_private_libreoffice_profile(monkeypatch):
    """Concurrent conversions sharing the default profile is a classic silent
    hang — every run must be isolated."""
    seen: list[list[str]] = []
    monkeypatch.setattr(convert.shutil, "which", lambda name: "/usr/bin/soffice")

    def run(cmd, capture_output=True, timeout=None, check=False):
        seen.append(cmd)
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        (outdir / "input.pdf").write_bytes(b"%PDF ok")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(convert.subprocess, "run", run)
    to_pdf(b"x", "a.pptx")
    to_pdf(b"x", "b.docx")
    profiles = [arg for cmd in seen for arg in cmd
                if arg.startswith("-env:UserInstallation=")]
    assert len(profiles) == 2 and profiles[0] != profiles[1]


def test_missing_libreoffice_says_so(monkeypatch):
    monkeypatch.setattr(convert.shutil, "which", lambda name: None)
    with pytest.raises(ConversionError, match="LibreOffice is not installed"):
        to_pdf(b"x", "deck.pptx")


def test_no_output_reports_libreoffices_own_message(monkeypatch):
    _fake_soffice(monkeypatch, writes=b"", returncode=1,
                  stderr=b"Error: source file could not be loaded")
    with pytest.raises(ConversionError, match="could not be loaded"):
        to_pdf(b"x", "deck.pptx")


def test_timeout_is_honest(monkeypatch):
    _fake_soffice(monkeypatch,
                  raises=subprocess.TimeoutExpired(cmd="soffice", timeout=180))
    with pytest.raises(ConversionError, match="timed out"):
        to_pdf(b"x", "deck.pptx", timeout=180)


def test_unstartable_binary_is_honest(monkeypatch):
    _fake_soffice(monkeypatch, raises=OSError("Exec format error"))
    with pytest.raises(ConversionError, match="could not be started"):
        to_pdf(b"x", "deck.pptx")


# --- storage keys -----------------------------------------------------------

def test_keys_keep_the_original_and_cache_the_rendering():
    src = doc_source_key("kb", "doc", "Présentation RH.pptx")
    assert src.endswith("/original.pptx")          # a .pptx stays a .pptx
    assert doc_source_key("kb", "doc", "a.PDF").endswith("/original.pdf")
    assert doc_converted_pdf_key("kb", "doc").endswith("/converted.pdf")
    # both live under the document prefix that delete/purge already wipes
    assert src.startswith("kbs/kb/docs/doc/")


# --- the ingest task treats a conversion failure as permanent ---------------

def test_conversion_failure_is_not_retried_as_transient():
    from tablerag.ingestion.tasks import _is_transient

    assert _is_transient(ConversionError("no LibreOffice")) is False
