"""Consume-folder discovery / mapping / stability — the pure helpers that decide
what gets ingested and into which KB. No DB, object store, or Celery needed."""

from tablerag.ingestion.consumer import (
    ARCHIVE_DIRNAME,
    archive_destination,
    discover_pdfs,
    is_stable,
    kb_name_from_path,
)


def _touch(path, content=b"%PDF-1.4\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_discover_pdfs_filters_hidden_archive_and_non_pdf(tmp_path):
    _touch(tmp_path / "ACCORDS" / "a.pdf")
    _touch(tmp_path / "ACCORDS" / "sub" / "b.pdf")
    _touch(tmp_path / "DHR" / "c.PDF")               # uppercase ext kept
    _touch(tmp_path / "root_level.pdf")              # discovered, but no KB
    _touch(tmp_path / "ACCORDS" / ".hidden.pdf")     # hidden -> skipped
    _touch(tmp_path / "notes.txt")                   # non-pdf -> skipped
    _touch(tmp_path / ARCHIVE_DIRNAME / "DHR" / "old.pdf")  # archive -> skipped

    found = {p.relative_to(tmp_path).as_posix() for p in discover_pdfs(tmp_path)}
    assert found == {"ACCORDS/a.pdf", "ACCORDS/sub/b.pdf", "DHR/c.PDF",
                     "root_level.pdf"}


def test_kb_name_from_path_is_the_first_subfolder(tmp_path):
    assert kb_name_from_path(tmp_path, tmp_path / "ACCORDS" / "a.pdf") == "ACCORDS"
    assert kb_name_from_path(tmp_path, tmp_path / "ACCORDS" / "s" / "b.pdf") == "ACCORDS"
    # a file directly in the root maps to no KB (ignored by the consumer)
    assert kb_name_from_path(tmp_path, tmp_path / "loose.pdf") is None


def test_is_stable_uses_mtime_age(tmp_path):
    pdf = _touch(tmp_path / "KB" / "a.pdf")
    mtime = pdf.stat().st_mtime
    assert is_stable(pdf, 5.0, now=mtime + 10)   # untouched for 10s -> stable
    assert not is_stable(pdf, 5.0, now=mtime + 1)  # 1s ago -> still settling
    assert not is_stable(tmp_path / "KB" / "missing.pdf", 5.0)  # gone -> not stable


def test_archive_destination_preserves_kb_and_dedupes(tmp_path):
    pdf = tmp_path / "ACCORDS" / "a.pdf"
    dest = archive_destination(tmp_path, pdf)
    assert dest == tmp_path / ARCHIVE_DIRNAME / "ACCORDS" / "a.pdf"
    # a clash gets a numeric suffix, never a clobber
    _touch(dest)
    assert archive_destination(tmp_path, pdf) == \
        tmp_path / ARCHIVE_DIRNAME / "ACCORDS" / "a_1.pdf"


def test_discover_pdfs_empty_root(tmp_path):
    assert discover_pdfs(tmp_path) == []
