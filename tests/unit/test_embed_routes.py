"""The only prefix the auth middleware lets through without an identity.

That is the risky part of this design, so most of what is tested here is what
the token CANNOT do.
"""

import contextlib

import pytest
from fastapi.testclient import TestClient

from tablerag.api.main import create_app
from tablerag.core.auth import OPEN_PREFIXES


def embed_paths() -> list[str]:
    """Every path the app publishes under the open prefix.

    Read from the OpenAPI schema rather than by walking `app.routes`: this
    FastAPI version keeps an included router as one opaque object there, so
    walking it finds nothing and a guard that finds nothing passes. The schema
    is also the right source — it is what the application publishes.
    """
    paths = create_app().openapi()["paths"]
    return [p for p in paths if p.startswith("/api/embed")]


@pytest.fixture
def client(monkeypatch):
    """A client whose embed routes find no assistant, without a database.

    session_scope opens a real connection; these tests are about what the routes
    do with a token that matches nothing, which needs no rows at all.
    """
    from tablerag.api.routes import embed

    @contextlib.contextmanager
    def no_database():
        yield None

    monkeypatch.setattr(embed, "session_scope", no_database)
    monkeypatch.setattr(embed.repo, "get_assistant_by_embed_token",
                        lambda s, token: None)
    return TestClient(create_app())


def test_the_embed_prefix_is_open_at_the_middleware():
    assert "/api/embed" in OPEN_PREFIXES


def test_every_embed_route_exchanges_a_token():
    """The guard for the door this design opens.

    Adding an endpoint under /api/embed and forgetting to resolve the token
    would publish it to anyone who can reach the port. Enumerated from what the
    application publishes, not from a list somebody maintains by hand.
    """
    paths = embed_paths()
    assert paths, "no embed routes registered"
    for path in paths:
        assert "{token}" in path, (
            f"{path} is under the open prefix but takes no token")


def test_an_unknown_token_is_not_found(client):
    assert client.get("/api/embed/nope").status_code == 404


def test_a_blank_token_is_not_found(client):
    assert client.get("/api/embed/%20%20").status_code == 404


def test_the_chat_route_carries_no_assistant_id():
    """A valid token must not be pointable at another assistant."""
    assert "/api/embed/{token}/chat" in embed_paths()
    assert not any("assistant_id" in p for p in embed_paths())
