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

**Add real scans too**: drop `image.png` + hand-written `ground_truth.json`
into a new `spike/tables/<your_id>/` folder — the synthetic set is a clean
lower bound, production PDFs are noisier.

## AMD RDNA4 warning (reference deployment, Appendix A.3)

Stock Ollama ships ROCm 6.x; RX 9070 XT (gfx1201) needs ROCm 7 → the GPU is
detected, hangs ~30 s, then **silently falls back to CPU**. In order:

1. `OLLAMA_VULKAN=1` (Vulkan backend, least driver pain) — try first
2. Community ROCm 7 build of Ollama — pin the version, auto-update overwrites the libs
3. llama.cpp directly (Vulkan/ROCm)

Verify with `ollama ps` (must say 100% GPU). `parse_table.py` also warns when
throughput < 5 tok/s.
