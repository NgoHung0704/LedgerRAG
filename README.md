# LedgerRAG

Self-hosted, multilingual document-RAG platform (Dify/RAGFlow-class) whose
competitive moat is **accurate parsing of complex PDF tables** — nested pivots,
multi-level headers, merged cells — with an uncompromising philosophy:

> **Parse it right, or fail honestly.** Every table keeps its original crop
> image, every parse carries a confidence flag, and the system says "I'm not
> sure — here is the original table" instead of ever inventing a number.

The full specification lives in [SPEC.md](SPEC.md) — it is the single source
of truth. Implementation follows its phases strictly.

## Phase status

| Phase | Content | Status |
|-------|---------|--------|
| 0 | De-risk spike: prove the parser VLM on the deployment hardware | **Campaign run** — champion `qwen3-vl:8b-instruct`, synthetic accuracy ~84–90% band (model non-determinism on deep rowspans); final go/no-go on real documents (see `spike/REPORT.md`) |
| 1 | Two-pipeline skeleton, text-only, end-to-end | **Code complete** — needs the Phase 1 DoD checks run against a live stack |
| 2 | Table sub-pipeline (three representations) | **Code complete** — layout detection, simple/VLM paths, locale-aware `core/numbers.py`, records+summaries indexed, tables in retrieval; validate with `make eval-tables` on the deployment box |
| 3 | Confidence & honest failure | **Code complete, detector being tuned** — 3 signals (structural / double-read / arithmetic), per-KB toggle, Approve / Mark-unusable review flow. First `make eval-flags` run FAILED the DoD (brittle double-read matching + mis-designed corruption set); both fixed (robust value-anchored agreement, grade-based eval) — awaiting re-run on the deployment box before this phase counts as done |
| 4 | Hybrid retrieval + answer verification | Not started (plugs exist) |
| 5 | Multi-KB router + end-user UX | Not started (plugs exist; model-provider admin UI shipped early) |

## Architecture (SPEC §2 — the four principles)

1. **The storage layer is the only contract.** `ingestion/` (write) and
   `query/` (read) never import each other — enforced by
   `tests/unit/test_architecture.py`. They meet in Postgres + Qdrant + object
   storage only.
2. **Records split `dimensions` / `metrics`** (JSONB), with `raw_values`
   always preserved.
3. **Every element traces to its origin**: `doc_id, page, bbox,
   crop_image_path, confidence` — answer → record → table → crop → PDF page.
4. **Router and Verification are pluggable steps**: the query pipeline is
   `Router → Retrieve → Rerank → AssembleContext → Generate → Verify`; Phase 1
   ships `SingleKBRouter`, pass-through rerank and a disabled `Verify`, all in
   their final slots.

```
tablerag/
  api/         FastAPI gateway (KB, documents, chat SSE, health)
  ingestion/   Celery worker: extract → chunk → embed → index (idempotent per doc)
  query/       pipeline steps (in-process, async, streaming)
  storage/     Postgres ORM + repositories, Qdrant wrapper, object store
  models/      ModelProvider interface + Ollama / OpenAI-compatible providers
  core/        config (pydantic-settings), schemas, logging, Celery app
frontend/      Next.js: KB management, upload + status, streaming chat with citations
spike/         Phase 0: standalone parser evaluation harness
tests/         unit + integration (+ eval suites from Phase 2)
```

## Model configuration (constraint C3 — nothing hardcoded)

Four abstract roles — `parser` (VLM), `embedder`, `chat`, `reranker` — each
mapped by the deploying engineer to an endpoint via env vars
(`LEDGERRAG_MODELS__<ROLE>__{PROVIDER,BASE_URL,MODEL_NAME,API_KEY}`, provider
∈ `ollama | openai_compat | disabled`). See [.env.example](.env.example).
`GET /api/health/models` reports per-role endpoint health.

On top of the env base, the **Model Providers page** (`/models` in the UI)
lets an admin change endpoints/models at runtime, browse the models installed
on an Ollama server, and pull new ones with streamed progress — overrides are
stored in Postgres (`app_setting`) and picked up by both the API and the
worker without restarts. For `qwen3-vl`, use the `-instruct` tag (the default
tag is a thinking model that returns empty output).

GPU assignment is the deployer's job (e.g. `ROCR_VISIBLE_DEVICES` per Ollama
instance) — the verified 3× AMD RX 9070 XT reference layout, including the
**RDNA4/ROCm silent-CPU-fallback trap**, is documented in SPEC Appendix A.

In local-only deployments (GDPR / data residency, constraint C1), point every
role at local endpoints and enable no API provider: there is no other network
egress in the data path.

## Quickstart

Prereqs: Docker; a model server (default: Ollama with `bge-m3`,
`mistral:latest`, and later `qwen2.5vl:7b` pulled).

```bash
cp .env.example .env       # adjust model endpoints
docker compose up -d --build
# frontend http://localhost:3000 · API http://localhost:8000/docs
```

Create a KB in the UI, drop a PDF on it, watch the status reach `done`, ask a
question — the answer streams with page-level citations that click through to
the stored page image.

### Phase 0 spike (run before building Phase 2)

```bash
python spike/make_test_tables.py    # generate 12-table multilingual test set
python spike/parse_table.py --all   # parse with the configured parser VLM
python spike/grade.py               # per-cell grading, 95% DoD gate
```

Fill in `spike/REPORT.md` with the results. If the gate fails: change the
model or backend and re-run — do not start Phase 2.

## Development

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .[dev]
pytest tests/unit -q                            # no services needed
RUN_INTEGRATION=1 pytest tests/integration -q   # needs docker compose stack
```

Rule from the spec: **prompts are code** — any prompt/model change must re-run
the relevant eval (`make spike-grade` now; `make eval-tables` / `make eval-qa`
from Phases 2/4) and paste results into the PR.
