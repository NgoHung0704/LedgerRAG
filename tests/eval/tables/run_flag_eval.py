"""Phase 3 flag eval — does the confidence layer know when the parse is wrong?

Runs the full production confidence path (parse + double-read + signals) over:
- spike/tables/       (clean)     -> should NOT be flagged  (precision)
- spike/tables_hard/  (corrupted) -> SHOULD be flagged      (recall)

DoD (SPEC Phase 3): clean tables falsely flagged <= 10%; corrupted tables
flagged >= 90%. Needs a live parser endpoint; ~2 VLM calls per table.

    python spike/make_test_tables.py && python spike/make_hard_tables.py
    python tests/eval/tables/run_flag_eval.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tablerag.core.config import get_settings  # noqa: E402
from tablerag.ingestion.confidence import assess  # noqa: E402
from tablerag.models.base import TableCtx  # noqa: E402
from tablerag.models.registry import get_provider  # noqa: E402

SPIKE = REPO_ROOT / "spike"


async def flag_one(image: bytes, locale: str) -> tuple[bool, str]:
    """Returns (flagged, reason) via the production confidence path."""
    settings = get_settings()
    parser = get_provider("parser")
    first = await parser.parse_table(image, TableCtx(locale_hint=locale))
    if first.error or not first.records:
        return True, "honest parse failure"
    second = await parser.parse_table(
        image, TableCtx(locale_hint=locale, read_variant=1))
    second_records = None
    if not second.error and second.records:
        second_records = [r.model_dump() for r in second.records]
    report = assess(
        first.html, [r.model_dump() for r in first.records], second_records,
        review_threshold=settings.confidence_review_threshold,
        agreement_threshold=settings.double_read_agreement_threshold)
    reason = ", ".join(f"{k}={v:.2f}" for k, v in
                       report.detail.get("signals", {}).items())
    return report.needs_review, reason


async def evaluate() -> int:
    sets = [("clean", SPIKE / "tables", False),
            ("corrupted", SPIKE / "tables_hard", True)]
    results: dict[str, list[tuple[str, bool, str]]] = {"clean": [], "corrupted": []}

    for set_name, folder, _ in sets:
        for gt_path in sorted(folder.glob("*/ground_truth.json")):
            gt = json.loads(gt_path.read_text(encoding="utf-8"))
            if gt.get("_draft"):
                continue
            image = (gt_path.parent / "image.png").read_bytes()
            flagged, reason = await flag_one(image, gt.get("locale", "unknown"))
            results[set_name].append((gt["table_id"], flagged, reason))
            mark = "FLAGGED" if flagged else "ok     "
            print(f"  [{set_name:9s}] {gt['table_id']:36s} {mark}  {reason}")

    if not results["corrupted"]:
        sys.exit("no corrupted tables — run `python spike/make_hard_tables.py`")

    clean_flagged = sum(1 for _, f, _ in results["clean"] if f)
    hard_flagged = sum(1 for _, f, _ in results["corrupted"] if f)
    n_clean, n_hard = len(results["clean"]), len(results["corrupted"])
    false_rate = clean_flagged / n_clean if n_clean else 0.0
    recall = hard_flagged / n_hard if n_hard else 0.0

    print(f"\nclean tables falsely flagged: {clean_flagged}/{n_clean} "
          f"= {false_rate:.0%}  (DoD <= 10%: "
          f"{'PASS' if false_rate <= 0.10 else 'FAIL'})")
    print(f"corrupted tables flagged:     {hard_flagged}/{n_hard} "
          f"= {recall:.0%}  (DoD >= 90%: {'PASS' if recall >= 0.90 else 'FAIL'})")
    return 0 if (false_rate <= 0.10 and recall >= 0.90) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(evaluate()))
