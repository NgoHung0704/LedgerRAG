"""Model-role management (constraint C3 made usable from the UI).

The deploying engineer — or an admin through the frontend — can inspect the
four roles, point them at different Ollama/OpenAI-compatible endpoints, list
what is installed on an Ollama server, and pull new models with streamed
progress. Everything here talks to infrastructure the deployer configured;
nothing is hardcoded.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from tablerag.core.schemas import (
    ModelRoleInfo,
    ModelRoleUpdate,
    OllamaModel,
    PullRequest,
)
from tablerag.models.registry import (
    MODEL_ROLES_SETTING,
    ROLES,
    check_role_health,
    effective_config,
    save_role_override,
)
from tablerag.storage.db import session_scope
from tablerag.storage.repositories import get_setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])


def _require_role(role: str) -> str:
    if role not in ROLES:
        raise HTTPException(404, f"unknown role {role!r}; roles: {', '.join(ROLES)}")
    return role


def _overridden_roles() -> set[str]:
    with session_scope() as s:
        return set((get_setting(s, MODEL_ROLES_SETTING) or {}).keys())


@router.get("", response_model=list[ModelRoleInfo])
async def list_roles() -> list[ModelRoleInfo]:
    overridden = await asyncio.to_thread(_overridden_roles)
    healths = await asyncio.gather(*(check_role_health(r) for r in ROLES))
    infos = []
    for role, health in zip(ROLES, healths):
        cfg = effective_config(role)
        infos.append(ModelRoleInfo(
            role=role, provider=cfg.provider, base_url=cfg.base_url,
            model_name=cfg.model_name, overridden=role in overridden,
            ok=health.ok, detail=health.detail))
    return infos


@router.put("/{role}", response_model=ModelRoleInfo)
async def update_role(role: str, body: ModelRoleUpdate) -> ModelRoleInfo:
    _require_role(role)
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(400, "nothing to update")
    await asyncio.to_thread(save_role_override, role, changes)
    cfg = effective_config(role)
    health = await check_role_health(role)
    return ModelRoleInfo(role=role, provider=cfg.provider, base_url=cfg.base_url,
                         model_name=cfg.model_name, overridden=True,
                         ok=health.ok, detail=health.detail)


@router.get("/{role}/available", response_model=list[OllamaModel])
async def available_models(role: str) -> list[OllamaModel]:
    """Models installed on the role's Ollama server (empty for other providers)."""
    _require_role(role)
    cfg = effective_config(role)
    if cfg.provider != "ollama" or not cfg.base_url:
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{cfg.base_url.rstrip('/')}/api/tags")
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, OSError) as e:
        raise HTTPException(502, f"Ollama endpoint unreachable: {e}") from e
    return [
        OllamaModel(name=m.get("name", ""), size_bytes=m.get("size"),
                    parameter_size=(m.get("details") or {}).get("parameter_size"))
        for m in data.get("models", [])
    ]


@router.post("/{role}/pull")
async def pull_model(role: str, body: PullRequest) -> StreamingResponse:
    """Pull a model onto the role's Ollama server, streaming progress as SSE."""
    _require_role(role)
    cfg = effective_config(role)
    if cfg.provider != "ollama" or not cfg.base_url:
        raise HTTPException(400, "pull is only available for Ollama endpoints")
    base_url = cfg.base_url.rstrip("/")

    async def progress():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                        "POST", f"{base_url}/api/pull",
                        json={"model": body.name, "stream": True}) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        event = {
                            "type": "progress",
                            "status": chunk.get("status", ""),
                            "total": chunk.get("total"),
                            "completed": chunk.get("completed"),
                        }
                        if chunk.get("error"):
                            event = {"type": "error", "message": chunk["error"]}
                        yield f"data: {json.dumps(event)}\n\n"
                        if chunk.get("error"):
                            return
            yield f'data: {json.dumps({"type": "done", "name": body.name})}\n\n'
        except (httpx.HTTPError, OSError, json.JSONDecodeError) as e:
            logger.exception("model pull failed (%s)", body.name)
            yield f'data: {json.dumps({"type": "error", "message": str(e)})}\n\n'

    return StreamingResponse(progress(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
