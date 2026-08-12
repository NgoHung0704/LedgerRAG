"""Which layer decided a role's endpoint, and whether that endpoint works.

Six times in one day the configuration that was written was not the
configuration that had effect: a database row beating .env, a flag missing from
the compose allow-list, code baked into an image, a client speaking the wrong
dialect. Every one was silent, and each cost a measurement.

The rule that made them silent is right - a model role that nobody configured
must degrade, not crash. But a role that IS configured and whose call fails is a
defect wearing the same clothes, and nothing told them apart.
"""

import logging

import pytest

from tablerag.models import registry


@pytest.fixture(autouse=True)
def _clean():
    registry.forget_role_failures()
    registry._overrides_cache.update({"value": {}, "ts": float("inf")})
    yield
    registry.forget_role_failures()
    registry._overrides_cache.update({"value": None, "ts": 0.0})


def test_a_database_override_is_named_as_the_winner(monkeypatch):
    monkeypatch.setenv("LEDGERRAG_MODELS__RERANKER__BASE_URL", "http://from-env")
    registry._overrides_cache["value"] = {
        "reranker": {"provider": "openai_compat", "base_url": "http://from-db"}}
    assert registry.config_source("reranker") == "database"


def test_the_environment_is_named_when_no_override_exists(monkeypatch):
    monkeypatch.setenv("LEDGERRAG_MODELS__RERANKER__BASE_URL", "http://from-env")
    assert registry.config_source("reranker") == "environment"


def test_a_role_nobody_touched_reads_as_default(monkeypatch):
    monkeypatch.delenv("LEDGERRAG_MODELS__RERANKER__BASE_URL", raising=False)
    assert registry.config_source("reranker") == "default"


def test_what_the_environment_says_is_still_visible_under_an_override(monkeypatch):
    monkeypatch.setenv("LEDGERRAG_MODELS__RERANKER__BASE_URL", "http://from-env")
    registry._overrides_cache["value"] = {"reranker": {"base_url": "http://from-db"}}
    assert registry.env_endpoint("reranker") == {"base_url": "http://from-env"}


def test_a_configured_role_that_fails_says_so_once(caplog):
    with caplog.at_level(logging.ERROR):
        registry.note_role_failure("reranker", RuntimeError("413 Payload Too Large"))
        registry.note_role_failure("reranker", RuntimeError("413 Payload Too Large"))
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1, "one ERROR per role, not one per query"
    assert "413" in errors[0].getMessage()


def test_the_failure_is_readable_afterwards():
    registry.note_role_failure("reranker", RuntimeError("boom"))
    failure = registry.role_failure("reranker")
    assert failure and "boom" in failure["error"]


def test_a_role_that_recovers_stops_being_reported():
    registry.note_role_failure("reranker", RuntimeError("boom"))
    registry.note_role_success("reranker")
    assert registry.role_failure("reranker") is None
