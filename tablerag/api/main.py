"""API gateway (FastAPI).

Run:  uvicorn tablerag.api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tablerag.core.config import get_settings
from tablerag.core.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    from tablerag.storage.db import init_db
    from tablerag.storage.qdrant import get_vector_store

    init_db()
    try:
        get_vector_store().ensure_collections()
    except Exception as e:  # noqa: BLE001 — API can start before Qdrant; ingestion re-ensures
        logger.warning("Qdrant not reachable at startup (%s); will retry on use", e)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="LedgerRAG", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from tablerag.api.routes import chat, documents, health, kb

    app.include_router(health.router)
    app.include_router(kb.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    return app


app = create_app()
