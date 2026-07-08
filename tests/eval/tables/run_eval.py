"""`make eval-tables` — the table-accuracy gate (SPEC Phase 2 §8).

Unlike the Phase 0 spike (which drives the model directly), this runs each
eval table through the PLATFORM's production parsing path
(ModelProvider.parse_table -> models/table_parsing contract, prompt included)
and grades per cell with the spike grader. Run it after ANY change to the
table prompt, the parser model, or the parsing code — prompt is code (§5).

Needs a live parser endpoint (env LEDGERRAG_MODELS__PARSER__*).

The eval set = spike/tables/ (12 synthetic multilingual tables + any real
documents added with spike/make_gt_template.py; drafts are skipped).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SPIKE_DIR = REPO_ROOT / "spike"
for p in (str(REPO_ROOT), str(SPIKE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import grade  # noqa: E402  (spike grader: matching + report)
from tablerag.core.config import get_settings  # noqa: E402
from tablerag.models.base import TableCtx  # noqa: E402
from tablerag.models.registry import get_provider  # noqa: E402


async def evaluate() -> int:
    tables_dir = SPIKE_DIR / "tables"
    gt_paths = sorted(tables_dir.glob("*/ground_truth.json"))
    if not gt_paths:
        sys.exit("no eval tables — run `python spike/make_test_tables.py` first")

    cfg = get_settings().models.parser
    print(f"eval-tables via PRODUCTION path — parser: {cfg.provider} "
          f"@ {cfg.base_url} model={cfg.model_name}\n")
    parser = get_provider("parser")

    results = []
    for gt_path in gt_paths:
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        if gt.get("_draft"):
            print(f"  {gt['table_id']:24s} skipped (draft ground truth)")
            continue
        image = (gt_path.parent / "image.png").read_bytes()
        parse = await parser.parse_table(
            image, TableCtx(locale_hint=gt.get("locale", "unknown")))
        if parse.error:
            parsed = {"error": parse.error}
        else:
            parsed = {"html": parse.html,
                      "records": [r.model_dump() for r in parse.records]}
        (gt_path.parent / "parsed.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        result = grade.grade_table(gt, parsed)
        accuracy = result["correct_cells"] / result["total_cells"] \
            if result["total_cells"] else 0.0
        note = "  [honest failure]" if result["honest_failure"] else ""
        print(f"  {gt['table_id']:24s} {result['correct_cells']:>4d}/"
              f"{result['total_cells']:<4d} {accuracy:>7.1%}{note}")
        results.append(result)

    total = sum(r["total_cells"] for r in results)
    correct = sum(r["correct_cells"] for r in results)
    overall = correct / total if total else 0.0
    print(f"\nOVERALL: {correct}/{total} = {overall:.1%}   "
          f"gate >= 95%: {'PASS' if overall >= 0.95 else 'FAIL'}")
    print("(details per miss: python spike/grade.py)")
    return 0 if overall >= 0.95 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(evaluate()))
