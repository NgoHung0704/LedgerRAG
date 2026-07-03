import pytest

from tablerag.storage.object_store import LocalFSStore, doc_pdf_key, page_image_key


def test_roundtrip(tmp_path):
    store = LocalFSStore(str(tmp_path))
    store.put("kbs/a/docs/b/original.pdf", b"%PDF-1.4 test")
    assert store.exists("kbs/a/docs/b/original.pdf")
    assert store.get("kbs/a/docs/b/original.pdf") == b"%PDF-1.4 test"


def test_missing_key(tmp_path):
    store = LocalFSStore(str(tmp_path))
    assert not store.exists("nope/missing.bin")
    with pytest.raises(FileNotFoundError):
        store.get("nope/missing.bin")


@pytest.mark.parametrize("bad_key", ["../escape.txt", "a/../../b", "/absolute/path"])
def test_unsafe_keys_rejected(tmp_path, bad_key):
    store = LocalFSStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.put(bad_key, b"x")


def test_key_layout_is_stable():
    assert doc_pdf_key("kb1", "doc1") == "kbs/kb1/docs/doc1/original.pdf"
    assert page_image_key("kb1", "doc1", 3) == "kbs/kb1/docs/doc1/pages/page-0003.png"
