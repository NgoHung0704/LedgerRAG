# Deploying LedgerRAG (self-host)

A practical guide for the customer's IT. LedgerRAG runs entirely on your own
machines — for GDPR/data-residency deployments, no document ever leaves the
box (constraint C1).

## 1. What you provide

- **A Linux host with Docker** (Engine + Compose v2).
- **A model server** the host can reach — Ollama is the default. It serves four
  roles; small deployments run them all on one Ollama, GPU permitting.
- **A GPU** for acceptable speed. NVIDIA is smoothest. For **AMD RDNA4
  (gfx1201, e.g. RX 9070 XT)** read §4 — there is a silent-CPU-fallback trap.

The Postgres / Qdrant / MinIO / API / worker / frontend containers are all in
`docker-compose.yml`; the model server is deliberately **not** (you run it where
the GPUs are and point the app at it — constraint C3).

## 2. Configure

```bash
cp .env.example .env
```

Set the four model roles in `.env` (`PROVIDER` ∈ `ollama | openai_compat |
disabled`). The configuration measured on the reference box:

| Role | Model | Note |
|------|-------|------|
| `PARSER` | `qwen3-vl:8b-instruct` | the table VLM — use the **`-instruct`** tag |
| `EMBEDDER` | `bge-m3` | dense + used for hybrid retrieval |
| `CHAT` | `qwen2.5:14b` | answers + routing; **not** the Coder variant |
| `RERANKER` | `bge-reranker-v2-m3` | via an OpenAI-compatible `/rerank` (vLLM or TEI); `disabled` is fine to start |

`BASE_URL` must be reachable **from inside the containers** — use the host's
LAN IP or `host.docker.internal`, and make sure the model server binds
`0.0.0.0`, not `127.0.0.1` (a loopback-only server is unreachable from a
container). Everything can also be changed later at runtime on the **Models**
page in the UI.

## 3. Start

```bash
docker compose up -d --build
# frontend  http://localhost:3000   ·   API http://localhost:8000/docs
bash scripts/preflight.sh           # verify GPU / endpoints (see §4)
```

Pull the models on the Ollama host if not present:
```bash
ollama pull qwen3-vl:8b-instruct && ollama pull bge-m3 && ollama pull qwen2.5:14b
```

The reranker (`bge-reranker-v2-m3`) needs an OpenAI-compatible `/rerank`
endpoint — vLLM serves it directly (`--task score`), or use the opt-in TEI
service (`docker compose --profile reranker up -d reranker`). Point the
reranker role at it, then confirm on the Models page that it is healthy.

## 4. GPU — the AMD RDNA4 trap

`bash scripts/preflight.sh` is the arbiter: it **times a short generation** and
fails when tokens/s is CPU-territory (<10). Trust that number, not "GPU
detected".

Stock Ollama ships ROCm 6.x, which **does not support gfx1201**: it detects the
card, hangs ~30s at discovery, and silently falls back to CPU (a few tokens/s,
no error). In order of least pain (SPEC Appendix A.3):

1. `OLLAMA_VULKAN=1` — Vulkan backend, avoids ROCm entirely. Try first.
2. A community ROCm-7 Ollama build for gfx1201 — pin the Ollama version so an
   auto-update can't overwrite the ROCm libs.
3. llama.cpp (Vulkan/ROCm) directly.

Verify with `ollama ps` (must read 100% GPU) and re-run preflight.

## 5. Use

Open `http://localhost:3000`, create a knowledge base (set its **number
locale**, e.g. `fr`), drag documents in, and wait for `done`. Then:

- **Describe** the KB (one click, "Suggest from documents") — the description
  is what the router reads to pick this KB in multi-KB chat.
- **Chat** answers with page-level citations; numbers are quoted exactly and a
  table read unreliably shows its original image instead of a guess.
- The **Review** tab lists any tables the parser flagged — check them against
  the original crop and approve, edit, or set aside.

## 6. Upgrading

After pulling a new version:
```bash
docker compose build --no-cache api worker && docker compose up -d
# only if a release note says the vector schema changed:
docker compose exec api python -m tablerag.scripts.reindex_all
```

## 7. Backups (GDPR / DR)

```bash
bash scripts/backup.sh /srv/ledgerrag-backups      # cron this; copy off-box
```
Dumps Postgres (parsed truth), Qdrant (vectors) and MinIO (crop images +
originals) with a checksum manifest; restore commands are printed at the end.

## 8. Validate a deployment

- `pytest tests/unit -q` — no services needed.
- `make eval-tables` — per-cell table-parse accuracy (needs the parser endpoint).
- `make eval-qa KB=<id>` — answer quality on your own question set.
- `make eval-routing` — routing accuracy across several KBs.

The eval question sets are assets: grow them from real questions (a 👎 in chat
is a question worth adding).

## 9. Authentication (multi-user / SSO)

LedgerRAG does not manage passwords. It trusts an **upstream reverse proxy**
(Authelia, oauth2-proxy, or your corporate SSO) to authenticate the user and
forward their identity in a header.

```env
LEDGERRAG_AUTH__MODE=proxy
LEDGERRAG_AUTH__USER_HEADER=X-Forwarded-User     # what your proxy sets
LEDGERRAG_AUTH__EMAIL_HEADER=X-Forwarded-Email
LEDGERRAG_AUTH__ADMINS=alice,boss@company.fr     # admins; everyone else = user
```

- **Admins** can change model-provider configuration and read the audit log;
  regular users create KBs, upload, and chat.
- Every **upload, query and config change is written to the audit log** with
  the user's identity (GDPR accountability) — visible at **Audit log** in the
  UI, or `GET /api/audit`.

> ⚠️ **Security**: trusting a header is safe **only** if the API is reachable
> *exclusively through the proxy*. If port 8000 is exposed directly, anyone can
> send `X-Forwarded-User: alice` and impersonate her. Put both the frontend and
> the API behind the same proxy, and do not publish the API port to untrusted
> networks. Leave `LEDGERRAG_AUTH__MODE=disabled` (the default) only for a
> single-tenant box on a trusted network — then everyone is one implicit admin.
