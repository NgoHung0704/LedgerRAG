"""Object storage for original PDFs and crop images.

Two backends behind one interface: MinIO (default in docker-compose) and a
local filesystem store (dev / single-box installs).
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Protocol

from tablerag.core.config import ObjectStoreConfig, get_settings


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes,
            content_type: str = "application/octet-stream") -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete_prefix(self, prefix: str) -> None: ...


def _safe_key(key: str) -> PurePosixPath:
    p = PurePosixPath(key)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unsafe object key: {key!r}")
    return p


class LocalFSStore:
    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / _safe_key(key)

    def put(self, key: str, data: bytes,
            content_type: str = "application/octet-stream") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete_prefix(self, prefix: str) -> None:
        import shutil

        path = self.root / _safe_key(prefix)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)


class MinIOStore:
    def __init__(self, cfg: ObjectStoreConfig):
        from minio import Minio

        self.client = Minio(cfg.endpoint, access_key=cfg.access_key,
                            secret_key=cfg.secret_key, secure=cfg.secure)
        self.bucket = cfg.bucket
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put(self, key: str, data: bytes,
            content_type: str = "application/octet-stream") -> None:
        key = str(_safe_key(key))
        self.client.put_object(self.bucket, key, io.BytesIO(data), len(data),
                               content_type=content_type)

    def get(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, str(_safe_key(key)))
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def exists(self, key: str) -> bool:
        from minio.error import S3Error

        try:
            self.client.stat_object(self.bucket, str(_safe_key(key)))
            return True
        except S3Error:
            return False

    def delete_prefix(self, prefix: str) -> None:
        from minio.deleteobjects import DeleteObject

        normalized = str(_safe_key(prefix)) + "/"
        objects = self.client.list_objects(self.bucket, prefix=normalized,
                                            recursive=True)
        errors = self.client.remove_objects(
            self.bucket, (DeleteObject(o.object_name) for o in objects))
        for _ in errors:  # drain iterator so deletes actually execute
            pass


def build_object_store(cfg: ObjectStoreConfig) -> ObjectStore:
    if cfg.backend == "minio":
        return MinIOStore(cfg)
    return LocalFSStore(cfg.root)


@lru_cache
def get_object_store() -> ObjectStore:
    return build_object_store(get_settings().object_store)


# canonical key layout
def doc_prefix(kb_id, doc_id) -> str:
    return f"kbs/{kb_id}/docs/{doc_id}"


def doc_pdf_key(kb_id, doc_id) -> str:
    return f"kbs/{kb_id}/docs/{doc_id}/original.pdf"


def page_image_key(kb_id, doc_id, page: int) -> str:
    return f"kbs/{kb_id}/docs/{doc_id}/pages/page-{page:04d}.png"
