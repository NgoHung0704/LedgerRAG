from tablerag.core.config import Settings


def test_nested_model_role_env_parsing(monkeypatch):
    monkeypatch.setenv("LEDGERRAG_MODELS__CHAT__PROVIDER", "openai_compat")
    monkeypatch.setenv("LEDGERRAG_MODELS__CHAT__BASE_URL", "http://gpu1:8001")
    monkeypatch.setenv("LEDGERRAG_MODELS__CHAT__MODEL_NAME", "ministral-8b")
    monkeypatch.setenv("LEDGERRAG_MODELS__RERANKER__PROVIDER", "disabled")
    monkeypatch.setenv("LEDGERRAG_EMBEDDING_DIM", "768")

    settings = Settings(_env_file=None)
    assert settings.models.chat.provider == "openai_compat"
    assert settings.models.chat.base_url == "http://gpu1:8001"
    assert settings.models.chat.model_name == "ministral-8b"
    assert settings.models.for_role("reranker").provider == "disabled"
    assert settings.embedding_dim == 768


def test_object_store_backend_switch(monkeypatch):
    monkeypatch.setenv("LEDGERRAG_OBJECT_STORE__BACKEND", "local")
    monkeypatch.setenv("LEDGERRAG_OBJECT_STORE__ROOT", "/srv/objects")
    settings = Settings(_env_file=None)
    assert settings.object_store.backend == "local"
    assert settings.object_store.root == "/srv/objects"


def test_no_model_is_hardcoded_as_requirement():
    """C3: every role is reconfigurable; defaults are only examples."""
    settings = Settings(_env_file=None)
    for role in ("parser", "embedder", "chat", "reranker"):
        endpoint = settings.models.for_role(role)
        assert endpoint.provider in ("ollama", "openai_compat", "disabled")
