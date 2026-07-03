"""Role -> provider resolution and endpoint health checks."""

from __future__ import annotations

from tablerag.core.config import EndpointConfig, ModelRole, get_settings
from tablerag.core.schemas import RoleHealth
from tablerag.models.base import ModelProvider


class RoleDisabled(Exception):
    """Raised when code asks for a role the deployer left disabled."""


def build_provider(cfg: EndpointConfig) -> ModelProvider:
    if cfg.provider == "ollama":
        from tablerag.models.ollama import OllamaProvider
        return OllamaProvider(cfg)
    if cfg.provider == "openai_compat":
        from tablerag.models.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(cfg)
    raise RoleDisabled(f"provider is disabled for this role (cfg={cfg.provider!r})")


_cache: dict[ModelRole, ModelProvider] = {}


def get_provider(role: ModelRole) -> ModelProvider:
    if role not in _cache:
        _cache[role] = build_provider(get_settings().models.for_role(role))
    return _cache[role]


def reset_providers() -> None:
    """For tests and config reloads."""
    _cache.clear()


async def check_role_health(role: ModelRole) -> RoleHealth:
    cfg = get_settings().models.for_role(role)
    if cfg.provider == "disabled":
        return RoleHealth(role=role, provider="disabled", model="", ok=True,
                          detail="role disabled by configuration")
    ok, detail = await get_provider(role).health()
    return RoleHealth(role=role, provider=cfg.provider, model=cfg.model_name,
                      ok=ok, detail=detail)
