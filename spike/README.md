# Phase 0 spike — prove the parser before building on it

Everything in this folder is standalone (no imports from `tablerag/`).
It answers one question: **does the chosen `parser` VLM, on the chosen
hardware, read complex pivot tables accurately enough (≥ 95% of cells)?**

If the answer is no, the spec says: change model or backend and re-run —
do **not** proceed to Phase 2.

## Run it (on the deployment machine)

```bash
pip install httpx pillow            # only deps needed by the spike
python spike/make_test_tables.py    # 1. generate 12 test tables + ground truth
python spike/parse_table.py --all   # 2. parse them with the parser endpoint
python spike/grade.py               # 3. per-cell grading, 95% DoD gate
```

Endpoint comes from env (same variables the platform uses) or flags:

```bash
python spike/parse_table.py --all \
    --provider ollama --base-url http://localhost:11434 --model qwen2.5vl:7b
```

Then fill in `REPORT.md`.

## Test set

`make_test_tables.py` renders 12 tables from single-source definitions
(image and ground truth can't drift): flat tables in EN/FR/DE/ES,
percentages + negatives, two-level headers, three nested pivots with
rowspan/colspan (including the spec's Afrique/Algérie/Citadine example with
`7 462 639 €`), a totals table, and a wide technical table. FR numbers use
the real narrow no-break space (U+202F).

**Add real scans too** — the synthetic set is a clean lower bound; the parser
is really decided by how it reads YOUR documents. The fast path from a
production PDF to a gradable case:

```bash
# render a page (optionally crop a region) + draft the ground truth with the
# parser itself, then correct the wrong cells by hand:
python spike/make_gt_template.py --id livret_salarie \
    --pdf livret.pdf --page 12 --locale fr --prefill
# edit spike/tables/livret_salarie/ground_truth.json, set "_draft": false, then
python spike/parse_table.py --image spike/tables/livret_salarie/image.png
python spike/grade.py
```

`grade.py` refuses to score a table while its GT still has `"_draft": true`, so
you can't accidentally grade the model against its own guess.

**Run-to-run variability:** at `temperature=0` an 8B VLM is still not
deterministic on nested-rowspan tables — the same table can score 100% one run
and lower the next. Treat the accuracy as a band, not a point; this is what the
Phase 3 double-read + confidence layer exists to handle.

## AMD RDNA4 warning (reference deployment, Appendix A.3)

Stock Ollama ships ROCm 6.x; RX 9070 XT (gfx1201) needs ROCm 7 → the GPU is
detected, hangs ~30 s, then **silently falls back to CPU**. In order:

1. `OLLAMA_VULKAN=1` (Vulkan backend, least driver pain) — try first
2. Community ROCm 7 build of Ollama — pin the version, auto-update overwrites the libs
3. llama.cpp directly (Vulkan/ROCm)

Verify with `ollama ps` (must say 100% GPU). `parse_table.py` also warns when
throughput < 5 tok/s.
