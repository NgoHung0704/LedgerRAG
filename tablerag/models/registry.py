"""Role -> provider resolution, runtime overrides, endpoint health checks.

Effective config per role = env/.env base (core/config.py) overlaid with the
`model_roles` row in app_setting (edited from the admin UI). The DB is read
on every resolution so the API process AND the Celery worker pick up changes
without restarts; providers are cached by their effective endpoint config.
"""

from __future__ import annotations

import logging

from tablerag.core.config import EndpointConfig, ModelRole, get_settings
from tablerag.core.schemas import RoleHealth
from tablerag.models.base import ModelProvider

logger = logging.getLogger(__name__)

MODEL_ROLES_SETTING = "model_roles"
ROLES: tuple[ModelRole, ...] = ("parser", "embedder", "chat", "reranker")


class RoleDisabled(Exception):
    """Raised when code asks for a role the deployer left disabled."""


def _overrides() -> dict:
    """Runtime overrides from Postgres; empty when the DB is unreachable so
    the platform still works from env config alone."""
    try:
        from tablerag.storage.db import session_scope
        from tablerag.storage.repositories import get_setting

        with session_scope() as s:
            return get_setting(s, MODEL_ROLES_SETTING) or {}
    except Exception:  # noqa: BLE001
        return {}


def effective_config(role: ModelRole) -> EndpointConfig:
    base = get_settings().models.for_role(role)
    override = _overrides().get(role) or {}
    data = base.model_dump()
    data.update({k: v for k, v in override.items()
                 if k in data and v not in (None, "")})
    return EndpointConfig(**data)


def save_role_override(role: ModelRole, changes: dict) -> None:
    from tablerag.storage.db import session_scope
    from tablerag.storage.repositories import get_setting, set_setting

    with session_scope() as s:
        overrides = get_setting(s, MODEL_ROLES_SETTING) or {}
        role_override = overrides.get(role) or {}
        role_override.update({k: v for k, v in changes.items() if v is not None})
        overrides[role] = role_override
        set_setting(s, MODEL_ROLES_SETTING, overrides)
    reset_providers()
    logger.info("model role %s updated: %s", role, role_override)


def build_provider(cfg: EndpointConfig) -> ModelProvider:
    if cfg.provider == "ollama":
        from tablerag.models.ollama import OllamaProvider
        return OllamaProvider(cfg)
    if cfg.provider == "openai_compat":
        from tablerag.models.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(cfg)
    raise RoleDisabled(f"provider is disabled for this role (cfg={cfg.provider!r})")


_cache: dict[tuple, ModelProvider] = {}


def get_provider(role: ModelRole) -> ModelProvider:
    cfg = effective_config(role)
    key = (role, cfg.provider, cfg.base_url, cfg.model_name, cfg.api_key)
    if key not in _cache:
        for stale in [k for k in _cache if k[0] == role]:
            del _cache[stale]  # this role's config changed
        _cache[key] = build_provider(cfg)
    return _cache[key]


def reset_providers() -> None:
    """For tests and config updates."""
    _cache.clear()


async def check_role_health(role: ModelRole) -> RoleHealth:
    cfg = effective_config(role)
    if cfg.provider == "disabled":
        return RoleHealth(role=role, provider="disabled", model="", ok=True,
                          detail="role disabled by configuration")
    ok, detail = await get_provider(role).health()
    return RoleHealth(role=role, provider=cfg.provider, model=cfg.model_name,
                      ok=ok, detail=detail)
