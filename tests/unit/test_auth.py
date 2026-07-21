"""Reverse-proxy auth: identity from a trusted header, admin from a list."""

import types

import pytest
from starlette.datastructures import Headers

from tablerag.core import auth
from tablerag.core.config import AuthConfig, Settings


def _settings(**auth_kw):
    s = Settings()
    s.auth = AuthConfig(**auth_kw)
    return s


def _request(headers: dict, user=None):
    req = types.SimpleNamespace()
    req.headers = Headers(headers)
    req.state = types.SimpleNamespace(user=user)
    req.url = types.SimpleNamespace(path="/api/kbs")
    req.method = "GET"
    return req


def test_disabled_mode_is_one_implicit_admin(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(mode="disabled"))
    u = auth.resolve_user(_request({}))
    assert u is not None and u.is_admin and u.username == "local"


def test_proxy_mode_no_header_is_unauthenticated(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(mode="proxy"))
    assert auth.resolve_user(_request({})) is None


def test_proxy_user_is_not_admin_by_default(monkeypatch):
    monkeypatch.setattr(auth, "get_settings",
                        lambda: _settings(mode="proxy", admins="boss@x.fr"))
    u = auth.resolve_user(_request({"X-Forwarded-User": "alice"}))
    assert u.username == "alice" and not u.is_admin


def test_admin_matched_by_username_or_email(monkeypatch):
    monkeypatch.setattr(
        auth, "get_settings",
        lambda: _settings(mode="proxy", admins="Alice, boss@x.fr"))
    by_name = auth.resolve_user(_request({"X-Forwarded-User": "alice"}))
    assert by_name.is_admin                      # case-insensitive name
    by_mail = auth.resolve_user(_request(
        {"X-Forwarded-User": "bob", "X-Forwarded-Email": "boss@x.fr"}))
    assert by_mail.is_admin                       # matched on email


def test_custom_header_name(monkeypatch):
    monkeypatch.setattr(
        auth, "get_settings",
        lambda: _settings(mode="proxy", user_header="Remote-User"))
    u = auth.resolve_user(_request({"Remote-User": "carol"}))
    assert u.username == "carol"


def test_require_admin_blocks_regular_user():
    user = auth.User(username="alice", email=None, is_admin=False)
    with pytest.raises(Exception) as e:
        auth.require_admin(user)
    assert "admin" in str(e.value).lower()


def test_current_user_401_when_unresolved():
    req = _request({}, user=None)
    with pytest.raises(Exception) as e:
        auth.current_user(req)
    assert "authenticated" in str(e.value).lower()
