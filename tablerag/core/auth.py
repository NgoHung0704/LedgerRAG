"""Reverse-proxy / SSO authentication (SPEC Phase 5).

The app does not manage passwords. An upstream proxy (Authelia, oauth2-proxy,
corporate SSO) authenticates the user and forwards their identity in a header;
we read it, decide admin vs user, and attach the identity for authorization and
the audit log.

SECURITY MODEL: trusting a header is safe ONLY when the API is reachable
exclusively through the proxy. If the API port is exposed directly, anyone can
send `X-Forwarded-User: admin`. Bind the API to the proxy's network and never
publish 8000 to untrusted networks. `mode=disabled` is dev/single-tenant: one
implicit admin, no header required.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from tablerag.core.config import get_settings

# open paths: health for load balancers, docs/schema for developers. Never
# gate these, or a proxy health check / the docs break.
OPEN_PREFIXES = ("/api/health", "/docs", "/redoc", "/openapi.json")


@dataclass(frozen=True)
class User:
    username: str
    email: str | None
    is_admin: bool


def _admin_set() -> set[str]:
    raw = get_settings().auth.admins
    return {a.strip().lower() for a in raw.split(",") if a.strip()}


def resolve_user(request: Request) -> User | None:
    """The authenticated user, or None when unauthenticated in proxy mode.
    In disabled mode everyone is the same implicit admin (dev/single-tenant)."""
    auth = get_settings().auth
    if auth.mode == "disabled":
        return User(username="local", email=None, is_admin=True)

    username = request.headers.get(auth.user_header)
    if not username:
        return None
    email = request.headers.get(auth.email_header)
    admins = _admin_set()
    is_admin = username.lower() in admins or (
        email is not None and email.lower() in admins)
    return User(username=username, email=email, is_admin=is_admin)


def current_user(request: Request) -> User:
    """FastAPI dependency: the request's user, or 401. The middleware has
    already resolved and cached it on request.state."""
    user: User | None = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(401, "not authenticated (no proxy identity header)")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "admin role required")
    return user


async def auth_middleware(request: Request, call_next):
    """Resolve the user once per request and gate everything but the open
    paths. Per-route authorization (admin) is enforced with require_admin."""
    request.state.user = resolve_user(request)
    path = request.url.path
    is_open = request.method == "OPTIONS" or any(
        path.startswith(p) for p in OPEN_PREFIXES)
    if request.state.user is None and not is_open:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"detail": "not authenticated"}, status_code=401)
    return await call_next(request)
