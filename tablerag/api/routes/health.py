import asyncio

from fastapi import APIRouter

from tablerag.core.schemas import RoleHealth
from tablerag.models.registry import check_role_health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/models", response_model=list[RoleHealth])
async def models_health() -> list[RoleHealth]:
    """Endpoint health per model role — the deployer's preflight view (C3)."""
    roles = ("parser", "embedder", "chat", "reranker")
    return list(await asyncio.gather(*(check_role_health(r) for r in roles)))
