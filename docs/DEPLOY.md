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

- **Disk**: the app image bundles LibreOffice (~500 MB) so Office documents can
  be converted to PDF for ingestion. Set `LEDGERRAG_OFFICE_CONVERT_ENABLED=false`
  if you only ever ingest PDFs and want to drop that from your own build.

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
locale**, e.g. `fr`), drag documents in, and wait for `done`. **PDF, Word
(.docx/.doc), PowerPoint (.pptx/.ppt) and Excel (.xlsx/.xls)** are accepted —
Office files are converted to PDF once, so they go through the same verified
table parsing and keep the same page-image provenance. Then:

- **Describe** the KB (one click, "Suggest from documents") — the description
  is what the router reads to pick this KB in multi-KB chat. When two KBs share
  vocabulary, spell out what sets them apart, or the router confuses them. A job
  grid keyed by "classe/groupe d'emploi" and a salary agreement also keyed by
  "classe d'emploi" look alike; say what each *uniquely* holds — e.g. the grid
  is "cotation (points), classification des postes, **pas de salaires**" and the
  agreement is "**salaires/montants en euros**, barèmes (unique + adaptés par
  groupe et ancienneté)". `make eval-routing` measures this.
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

### Every build leaves the old images behind — reclaim, or the box fills up

`docker compose up --build` retags the new image and leaves the previous one
**untagged**, not deleted. Three services at ~940 MB each, rebuilt through a
working week, is how MIA-82025 reached 387 images and **100 % of a 466 GB disk**
on 2026-08-20. The symptoms did not point at disk at all:

- Ollama answering **HTTP 500** on `/api/chat`, so every question failed with
  "internal error" — the traceback blamed the model, not the filesystem;
- `docker compose up --build` dying on `no space left on device`.

`make deploy` does the whole thing in the right order. The order is the point:

```bash
docker compose up -d --build   # containers switch to the NEW image
docker image prune -f          # only now is the previous build unreferenced
```

Pruning first frees nothing — the old image is still in use by the running
container, so it is skipped and the orphan survives. And `docker compose down`
does not help either way: the image is orphaned by its tag moving to the new
build, which has nothing to do with whether containers are up.

Reclaim is safe on a shared box, since it only removes images no container
references. Add `docker builder prune -f` when the build cache has grown.

`docker system df` shows where the space went. Two cautions, both learned the
hard way on this box:

- **Never `docker system prune --volumes`.** `pgdata`, `qdrant_data` and
  `minio_data` are named volumes: that flag deletes every knowledge base,
  parsed document and vector, unrecoverably.
- **`docker image prune -a` is not safe on a shared machine.** It removes any
  image without a *running* container, including other projects' stopped ones —
  and a 38 GB vLLM image is a long download to get back.

Check where large models actually live before touching their containers. On
this box Ollama's weights sit in the **container's writable layer**, not a
volume, so `docker rm ollama` would discard them all. `docker ps -as` prints
the writable size per container and tells you which ones hold data they should
not. Note the path: the weights were under `/modelfiles` (`OLLAMA_MODELS`), and
`/root/.ollama` held 4 KB of SSH keys — copying "the obvious" directory to a
volume would have moved nothing.

### A crashing model server fills the disk with its own crash dumps

The 118 GB in that container was not models. It was **90 core dumps totalling
85 GB** — one per Ollama crash, ~1 GB each, plus a 16 GB `core.gpu` — written
into the container's root because the host's `kernel.core_pattern` puts them in
the working directory. Models were 23 GB of it.

They are crash artefacts and nothing reads them, so deleting is safe:

```bash
docker exec <container> sh -c 'ls -d /core.* | wc -l'   # count first
docker exec <container> sh -c 'du -ch /core.* | tail -1'
docker exec <container> sh -c 'rm -f /core.*'
```

**The count is the real finding.** Ninety crashes is a systematically unstable
service, not bad luck, and on RDNA4 it points straight at §4. The disk failure
was the symptom: each crash wrote a gigabyte, ninety of them filled the disk,
and a full disk is what finally stopped the restarts from working. Clear the
dumps and they grow back unless the crashes stop.

Containers that crash should not be allowed to dump at all — `--ulimit core=0`
at `docker run` (it cannot be changed later with `docker update`). Worth setting
on any model server, since their core dumps are the size of their VRAM.

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
- `make eval-followup` — multi-turn: does a fragment follow-up resolve against
  the thread? `ARGS="--ablate --auto-route"` shows the lift memory provides.

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
