# Phase 0 spike report — parser model × deployment hardware

> Template. Fill in after running the spike **on the deployment machine**.
> Re-run and re-fill this report every time the parser model OR the hardware
> changes (SPEC Phase 0: this is a process, not a one-off).

## Status: IN PROGRESS — model selection done, prompt iteration running

Phase 0 DoD is **not met** until every box below is checked with real numbers.
Per SPEC, do not build Phase 2 (table sub-pipeline) on top of an unverified
parser assumption. Phase 1 (text-only skeleton) does not depend on the parser.

**Campaign so far (2026-07, host MIA-82025, Ollama on :11435):** GPU execution
verified (steady 77–88 tok/s, no load hang). Model comparison selected
`qwen3-vl:8b-instruct` as champion — with prompt v2 it reads **every number
correctly** on flat/wide tables (100% strict) and all remaining losses were
three structural motifs (dropped header level, wide-instead-of-long records,
measures split via a `metric_type` dimension), addressed in prompt v3 +
pooled grading. **Trap:** the default `qwen3-vl` tag is a *thinking* model
that returns empty output via `/api/chat` — the `-instruct` tag is required.

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

| Attempt | Model | Stack | tok/s | Cell accuracy (relaxed) | Verdict |
|---------|-------|-------|-------|-------------------------|---------|
| 1 | qwen2.5vl:7b | Ollama @ :11435 | ~87 | 5.3% | FAIL — structure + contract violations |
| 2 | granite (vision) | Ollama @ :11435 | | 6.3% | FAIL |
| 3 | minicpm-v | Ollama @ :11435 | | 3.2% | FAIL |
| 4 | qwen3-vl:8b-instruct (prompt v2) | Ollama @ :11435 | ~78 | 45.5% (flat+wide 100% strict; all numbers read correctly, misses purely structural) | champion — prompt v3 iteration |
| 5 | qwen3-vl:8b-instruct (prompt v3 + pooled grading) | Ollama @ :11435 | | _run me_ | |
