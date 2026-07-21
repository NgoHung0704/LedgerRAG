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
| 2 | Table sub-pipeline (three representations) | **Measured on the box (first production-path run, 2026-07-20): `make eval-tables` = 88.4%** — above the Phase 0 direct-drive band (84–90%) after the duplicate-dimensions contract (a dropped header level leaves two records with identical dims; the retry names the offending pair and recovers the table — pivot_de_umsatz 0/16 → 16/16). The **≥95% gate is not met with `qwen3-vl:8b-instruct`**: the remaining misses are deep-pivot sub-row misattribution (unique-but-wrong labels, no structural fingerprint — same family as the Phase 3 finding, SPEC §7). Parser-model upgrade is the lever (C3 makes the swap config-only). **Never edit the parser prompt without an isolated eval-tables A/B: wording changes flip unrelated tables between 0% and 100%.** |
| 3 | Confidence & honest failure | **Done, with a documented limit** — 3 signals (structural / double-read / arithmetic), review flow. Measured on the box: false-positive rate **0%** ✓, but auto-recall on systematic misreads is fundamentally low (a single small model can't self-detect confident errors; cross-model verifiers measured, all worse). The **≥90% recall DoD is not achievable on this hardware** (SPEC §7 open risk); the real safety net is architectural (source image always kept + answers never assert numbers from a flagged parse + human review). See `spike/REPORT.md` §4c. |
| 4 | Hybrid retrieval + answer verification | **Gate passed on the box (2026-07-21): `make eval-qa` = table 19/20 (95%), text 12/12 (100%), traps 7/7 (100%)** on a 39-question set over three real French HR PDFs. Answer-number verification (locale-aware + arithmetic whitelist, UI badges); hybrid dense+sparse retrieval (local lexical sparse + Qdrant IDF, RRF fusion, dense-only fallback); Rerank step (cross-encoder, honest degradation when disabled/down); document-diversified fallback ordering; `make eval-qa` harness. **The measured config:** chat `qwen2.5:14b`, reranker `bge-reranker-v2-m3` behind an OpenAI-compatible endpoint (the box reused its existing vLLM). **To activate:** `reindex_all` migration, point the reranker role at a `/rerank` endpoint, fill `questions.jsonl` with real pairs. One documented miss (a1): two same-shaped pay scales in one document that vague auto-summaries can't disambiguate — a retrieval hard case, not a parse or honesty failure. |
| 5 | Multi-KB router + end-user UX | **Code complete** — `LLMRouter` over KB descriptions (multi-select, manual-pin override, degrade-to-all on failure) in the Phase-1 router slot; multi-KB chat (`POST /api/chat`); `make eval-routing` (recall vs exact, scored apart from answers); one-click KB-description drafting. End-user UX: chat KB-scope selector + routed-to badge, KB-level review queue, 👍/👎. Reverse-proxy/SSO auth (admin/user, header-trusted) + GDPR audit log (upload/query/config). Packaging: `scripts/preflight.sh` (catches the AMD CPU-fallback trap by timing tokens/s), `scripts/backup.sh`, `docs/DEPLOY.md`. **Remaining is deployment-side validation (DoD): 3 real KBs × 10 routing questions ≥90%, an unassisted HR-colleague run, and `docker compose up` on a clean GPU box.** |

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
