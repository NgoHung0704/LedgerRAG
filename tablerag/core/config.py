"""Platform configuration.

Constraint C3: the platform is model- and hardware-agnostic. The four model
roles (parser / embedder / chat / reranker) are abstract; the deploying
engineer maps each to a concrete endpoint via environment variables
(prefix LEDGERRAG_, nested delimiter "__") or a .env file. Nothing here may
hardcode a model name as a *requirement* — defaults are examples only.

Constraint C1: in a local-only deployment every base_url points at
infrastructure the customer controls; there is no other network egress in the
data path.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ModelRole = Literal["parser", "embedder", "chat", "reranker"]


class EndpointConfig(BaseModel):
    """One model role -> one serving endpoint, chosen by the deployer."""

    provider: Literal["ollama", "openai_compat", "disabled"] = "disabled"
    base_url: str = ""
    model_name: str = ""
    api_key: str | None = None


class ModelsConfig(BaseModel):
    parser: EndpointConfig = EndpointConfig(
        provider="ollama", base_url="http://localhost:11434",
        model_name="qwen3-vl:8b-instruct")
    embedder: EndpointConfig = EndpointConfig(
        provider="ollama", base_url="http://localhost:11434", model_name="bge-m3")
    chat: EndpointConfig = EndpointConfig(
        provider="ollama", base_url="http://localhost:11434", model_name="mistral:latest")
    reranker: EndpointConfig = EndpointConfig()  # disabled = pass-through (Phase 1)

    def for_role(self, role: ModelRole) -> EndpointConfig:
        return getattr(self, role)


class ObjectStoreConfig(BaseModel):
    backend: Literal["minio", "local"] = "local"
    # local backend
    root: str = "./data/objects"
    # minio backend
    endpoint: str = "localhost:9000"
    access_key: str = "ledgerrag"
    secret_key: str = "ledgerrag-secret"
    bucket: str = "ledgerrag"
    secure: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEDGERRAG_", env_nested_delimiter="__",
        env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ledgerrag:ledgerrag@localhost:5432/ledgerrag"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    object_store: ObjectStoreConfig = ObjectStoreConfig()
    models: ModelsConfig = ModelsConfig()

    # must match the configured embedder's output dimension (bge-m3 = 1024)
    embedding_dim: int = 1024

    chunk_target_tokens: int = 500
    chunk_overlap_ratio: float = 0.10
    retrieve_top_k: int = 12       # final context size when no reranker
    retrieve_candidates: int = 50  # hybrid candidate pool fed to the reranker
    rerank_top_k: int = 8          # final context size after reranking

    # table-parsing generation options — proven out in the Phase 0 spike.
    # num_ctx MUST be large: the few-shot prompt + a vision image easily
    # exceeds Ollama's default context, silently truncating the prompt and
    # degrading structural accuracy (this is what dropped the production eval
    # ~10 points below the spike until it was fixed).
    table_parse_num_ctx: int = 8192
    table_parse_num_predict: int = 4096
    table_parse_seed: int = 0

    # verification layer (Phase 4) — pluggable step exists from Phase 1 (principle #4)
    verification_enabled: bool = False

    # Phase 3 confidence layer (SPEC: thresholds are config, tuned on the
    # eval set — never guessed in code review)
    double_read_enabled: bool = True  # per-KB override: kb.config["double_read"]
    double_read_agreement_threshold: float = 0.98
    confidence_review_threshold: float = 0.9
    # cross-model double-read: same-model re-reads reproduce systematic errors
    # (confident + wrong + identical twice -> agreement 1.0 -> not flagged), so
    # a genuinely independent second opinion needs a DIFFERENT architecture.
    # Empty = fall back to same-model seed-shift.
    double_read_model_name: str = ""
    double_read_base_url: str = ""  # empty = reuse the parser base_url

    # ingestion: pages with fewer stripped chars are flagged as needing OCR
    scan_min_chars_per_page: int = 32
    page_render_dpi: int = 120
    # table crops are re-rendered from the PDF at this DPI (real pixels beat
    # interpolation) — dense tables at 120 dpi lose digits to the VLM
    table_crop_dpi: int = 240
    # images sent to the VLM are upscaled to at least this width (scans)
    vlm_min_image_width: int = 1400

    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
