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


class AuthConfig(BaseModel):
    """Reverse-proxy / SSO auth (SPEC Phase 5). The app trusts an upstream
    proxy (Authelia, oauth2-proxy, corporate SSO) that authenticates the user
    and forwards their identity in a header. SECURITY: this is safe ONLY when
    the API is reachable exclusively through that proxy — a directly-exposed
    API lets anyone spoof the header. `disabled` (default) is dev/single-tenant:
    one implicit admin, no header required."""
    mode: Literal["disabled", "proxy"] = "disabled"
    user_header: str = "X-Forwarded-User"   # oauth2-proxy / Authelia default
    email_header: str = "X-Forwarded-Email"
    # comma-separated usernames/emails that get the admin role; everyone else
    # is a regular user. Empty in proxy mode = nobody is admin (lock infra down).
    admins: str = ""


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
    # Qdrant REST timeout (seconds). The client library defaults to 5s, which a
    # bulk upload trips: many workers issue synchronous upsert(wait=True) at once
    # and each request queues past 5s -> ResponseHandlingException: timed out ->
    # the doc is marked failed (and concurrent chat searches fail the same way).
    # Widen it so a busy Qdrant is waited on, not abandoned; writes also batch +
    # retry per request (storage/qdrant.py) so this is the per-attempt ceiling.
    qdrant_timeout: int = 120
    object_store: ObjectStoreConfig = ObjectStoreConfig()
    models: ModelsConfig = ModelsConfig()
    auth: AuthConfig = AuthConfig()

    # must match the configured embedder's output dimension (bge-m3 = 1024)
    embedding_dim: int = 1024

    chunk_target_tokens: int = 500
    chunk_overlap_ratio: float = 0.10
    retrieve_top_k: int = 12       # final context size when no reranker
    # off until measured: expansion changes citation counts, so eval-qa must be
    # re-run A/B before it can become the default
    expand_neighbours: bool = False
    retrieve_candidates: int = 50  # hybrid candidate pool fed to the reranker
    rerank_top_k: int = 8          # final context size after reranking
    # of those slots, how many are held for record / table-summary hits. A
    # cross-encoder scores whether a PASSAGE answers a question, so a table row
    # loses to prose every time: measured on the box, a balanced candidate pool
    # came out as 8 chunks and nothing else on 10 queries out of 10, and the
    # table sub-pipeline was absent from the context it exists to fill.
    # 0 disables the reservation.
    rerank_reserve_structured: int = 3

    # table-parsing generation options — proven out in the Phase 0 spike.
    # num_ctx MUST be large: the few-shot prompt + a vision image easily
    # exceeds Ollama's default context, silently truncating the prompt and
    # degrading structural accuracy (this is what dropped the production eval
    # ~10 points below the spike until it was fixed).
    table_parse_num_ctx: int = 8192
    table_parse_num_predict: int = 4096
    table_parse_seed: int = 0

    # verification layer (Phase 4) — pluggable step exists from Phase 1
    # (principle #4). Default ON: it is the honesty net for number questions
    # and for KBs created before the per-KB toggle existed (their config has
    # no "verify" key and falls back to this).
    verification_enabled: bool = True

    # "double-check" on a table: the region is re-rendered at this resolution
    # for the verification pass, which faults the first reading against the
    # image. Higher than the re-parse DPI on purpose — the check is the careful
    # look. Set it at or below the re-parse DPI to reuse the same render.
    table_verify_dpi: int = 600

    # Office documents (.pptx/.docx/.xlsx) are converted to PDF with LibreOffice
    # before ingestion, so the measured PDF pipeline (page renders, table
    # detection, crops, citations) applies unchanged. Disable to accept PDFs only.
    office_convert_enabled: bool = True
    office_convert_timeout: int = 180

    # answer a greeting as a greeting instead of running it through routing +
    # retrieval and reporting "no relevant passages". Detection is
    # deterministic and conservative (query/steps/smalltalk.py); turn it off to
    # send every message, including "salut", down the retrieval path.
    smalltalk_enabled: bool = True

    # answer generation context — same silent-truncation trap as the parser
    # (see table_parse_num_ctx below): the assembled sources easily exceed
    # Ollama's default num_ctx, which then drops the TOP of the prompt — the
    # system rules and the highest-ranked sources — while the answer still
    # streams normally. Must cover retrieve_top_k blocks incl. table HTML.
    chat_num_ctx: int = 32768
    # held back from chat_num_ctx for the system prompt and the answer itself,
    # so assembled sources can never push SYSTEM_PROMPT off the top
    context_reserve_tokens: int = 3000
    # answers must be reproducible: the same question on unchanged documents
    # has to give the same figures. Left unset, Ollama samples at 0.8 and the
    # same question flip-flopped between right and wrong across eval runs.
    chat_temperature: float = 0.0

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
    # A figure carries no text layer, so without this it is stored for
    # provenance and is invisible to search. The parser VLM describes it and
    # the description is indexed — marked as a description, never as text read
    # off the page. The cap bounds what one pathological document can cost.
    figure_describe_enabled: bool = True
    figure_describe_max_per_doc: int = 30
    # A vector chart's bars are measurable, so the numbers a model claims to
    # have read off it can be checked against them. Measured on a fund
    # factsheet: a correct reading scores 0.998, a single transposed digit
    # 0.55, an invented value 0.80. Below this the figure goes to Review.
    figure_chart_min_agreement: float = 0.95

    # consume folder (Paperless-style bulk ingest). Empty = disabled. Drop PDFs
    # into consume_dir/<KB name>/*.pdf; the consumer service (tablerag.ingestion
    # .consumer) polls, ingests into that KB (created if missing), and archives
    # the file. A file is only taken once unmodified for consume_stability_secs,
    # so a half-copied upload is never grabbed.
    consume_dir: str = ""
    consume_interval: float = 5.0
    consume_stability_secs: float = 5.0

    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
