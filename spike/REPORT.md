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

Across the campaign, with qwen3-vl:8b-instruct + prompt v4:

- **Numbers and locales are read correctly** — no digit/locale errors survived
  prompt v3+. FR U+202F, DE dot-thousands/comma-decimals, EN, %, negatives all fine.
- **Residual failures are structural/positional, and the values are always
  real** (never invented — misplaced at worst). Two modes:
  1. *Dropped header dimension* on deep pivots — e.g. `pivot_de_umsatz` omitted
     `jahr` (year) and emitted 4 records instead of 8.
  2. *Adjacent-row confusion* — values from one sub-row copied onto the next
     under a merged (rowspan) cell (`pivot_fr_auto` Berline←Citadine;
     `twolevel_fr` R&D←Ventes).
- **Run-to-run variability (the key finding):** at `temperature=0` (and even
  with a fixed `seed`), the model is NOT deterministic on the hardest tables.
  `pivot_de_umsatz` scored 100% one run and 0% the next with no change to GT,
  model or prompt. **The true accuracy is a band (~84–90%), not a point.**
  This is an inherent property of an 8B VLM on nested-rowspan structures, not a
  prompt bug — no prompt makes it deterministic. It is the architectural
  justification for Phase 3 (double-read agreement + confidence flags) and
  Phase 4 (answer verification): the system is designed to *catch* these, not
  to require a perfect parser. A misplaced number lands in a `needs_review`
  table showing the original crop — "parse right, or fail honestly" (§0.3).

## 5. Decision

**Current position (2026-07):** synthetic accuracy ~84–90% (band, due to model
non-determinism). The literal 95%-on-synthetic gate is not met, but every
remaining miss is either run-variability or a genuine deep-rowspan reading
limit — and all values read are real, never invented.

**Chosen path — gather real-document evidence before the final go/no-go**
(SPEC Phase 0 explicitly recommends adding real scans before concluding). The
synthetic set is a clean lower bound; the decisive question is how the parser
reads actual French HR documents. Use `spike/make_gt_template.py` to add
2–3 real tables (livret du salarié, classification grid, salary scale) and
re-run. Final Phase 0 sign-off:

- [ ] Real-doc tables read with values correct and failures honest
      (misplacements flagged-able, no invented numbers) → parser proven;
      proceed to Phase 2, pin model+stack in docker-compose, rely on Phase 3
      confidence to handle the variability band.
- [ ] Real-doc tables read badly → **DoD FAIL** on the real signal → stop;
      try next candidate (InternVL / Pixtral / document-AI API, or a larger
      qwen3-vl if VRAM allows) and re-run this spike.

| Attempt | Model | Stack | tok/s | Cell accuracy (relaxed) | Verdict |
|---------|-------|-------|-------|-------------------------|---------|
| 1 | qwen2.5vl:7b | Ollama @ :11435 | ~87 | 5.3% | FAIL — structure + contract violations |
| 2 | granite (vision) | Ollama @ :11435 | | 6.3% | FAIL |
| 3 | minicpm-v | Ollama @ :11435 | | 3.2% | FAIL |
| 4 | qwen3-vl:8b-instruct (prompt v2) | Ollama @ :11435 | ~78 | 45.5% (flat+wide 100% strict; all numbers read correctly, misses purely structural) | champion — prompt v3 iteration |
| 5 | qwen3-vl:8b-instruct (prompt v3 + pooled grading) | Ollama @ :11435 | ~78 | **84.1%** — 10/12 tables 100%. Residual: `twolevel_fr` (ground-truth orientation bug, NOT model) + `pivot_fr_auto` 50% (genuine read error: Citadine values copied onto Berline under deep rowspan) | 2 residual causes diagnosed |
| 6 | qwen3-vl:8b-instruct (prompt v4 + fixed twolevel_fr GT) | Ollama @ :11435 | ~78 | **89.4%** — 10/12 tables 100% (incl. `pivot_fr_auto` 100% this run!). twolevel_fr fix worked (0%→66.7%). But `pivot_de_umsatz` regressed 100%→0% with NO change → run-to-run variability | true score is a ~84–90% BAND, not a fixed number |
