# Phase 0 spike report — parser model × deployment hardware

> Template. Fill in after running the spike **on the deployment machine**.
> Re-run and re-fill this report every time the parser model OR the hardware
> changes (SPEC Phase 0: this is a process, not a one-off).

## Status: NOT YET RUN

Phase 0 DoD is **not met** until every box below is checked with real numbers.
Per SPEC, do not build Phase 2 (table sub-pipeline) on top of an unverified
parser assumption. Phase 1 (text-only skeleton) does not depend on the parser.

## 1. Environment

| Item | Value |
|------|-------|
| Hardware (GPU) | _e.g. 3× AMD RX 9070 XT (gfx1201, 16 GB)_ |
| Serving stack | _e.g. Ollama + `OLLAMA_VULKAN=1` / community ROCm 7 build / llama.cpp_ |
| Why this stack | _e.g. stock Ollama ships ROCm 6.x → silent CPU fallback on RDNA4 (Appendix A.3)_ |
| Parser model | _e.g. qwen2.5vl:7b-q4_ |
| Ollama/backend version (pinned) | |

## 2. GPU verification (DoD item 1)

- [ ] `ollama ps` reports **100% GPU** (not CPU/partial) while parsing
- [ ] Throughput: ______ tok/s (parse_table.py prints this; < 5 tok/s ⇒ suspect CPU fallback)
- [ ] No ~30 s hang at model load (RDNA4 ROCm-6 discovery symptom)

## 3. Results (DoD items 2–3)

How to produce:

```bash
python spike/make_test_tables.py     # generate test set (12 tables, EN/FR/DE/ES)
python spike/parse_table.py --all    # parse with the configured endpoint
python spike/grade.py                # per-cell grading, 95% gate
```

Paste the grade.py report here:

```
(output of python spike/grade.py)
```

- [ ] Overall cell accuracy ≥ 95%
- [ ] `pivot_fr_auto` (spec flagship: 3-level header, nested rowspans) parses with correct structure (inspect its `parsed.json` HTML by hand)
- [ ] Locale numbers survive: FR `7 462 639` (U+202F), DE `7.462.639,50`, EN `7,462,639.50`, `12,5 %`, negatives — spot-check `raw_values` by hand
- [ ] Real scanned tables (add your own under `spike/tables/<id>/` with a hand-written `ground_truth.json`) — the synthetic set is clean-render; production PDFs are noisier

## 4. Error patterns observed

_List every recurring mistake (digit confusion, dropped rows, merged-cell mixups,
locale misreads...). Phase 2 prompt engineering starts from this list._

## 5. Decision

- [ ] **DoD PASS** → proceed to Phase 2 table sub-pipeline with this model+stack (pin versions in docker-compose)
- [ ] **DoD FAIL** → stop; try next candidate (InternVL / Pixtral / document-AI API) and re-run this spike

| Attempt | Model | Stack | tok/s | Cell accuracy | Verdict |
|---------|-------|-------|-------|---------------|---------|
| 1 | | | | | |
