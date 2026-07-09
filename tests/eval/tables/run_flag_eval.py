"""Phase 3 flag eval — does the confidence flag predict a WRONG parse?

Honest design (v2): a corrupted image is not automatically a wrong parse — a
robust VLM often reads through mild blur/rotation. So each table is parsed
AND graded against ground truth to learn whether the stored read is actually
correct; the confidence flag is then measured against real correctness:

  - actually-correct parses that get flagged      -> false positives (want low)
  - actually-wrong parses that get flagged         -> caught (want high)

DoD (SPEC Phase 3 intent): false-positive rate <= 10%, recall on wrong
parses >= 90%. Needs a live parser endpoint; ~2 VLM calls per table.

    python spike/make_test_tables.py && python spike/make_hard_tables.py
    python tests/eval/tables/run_flag_eval.py

The corrupted set widens the pool of genuinely-wrong parses; whether each is
wrong is decided by grading, never assumed.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SPIKE = REPO_ROOT / "spike"
for p in (str(REPO_ROOT), str(SPIKE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import grade  # noqa: E402  (spike grader)
from tablerag.core.config import get_settings  # noqa: E402
from tablerag.ingestion.confidence import assess  # noqa: E402
from tablerag.models.base import TableCtx  # noqa: E402
from tablerag.models.registry import get_double_read_provider, get_provider  # noqa: E402

CORRECT_CELL_THRESHOLD = 0.95


@dataclass
class Outcome:
    table_id: str
    correct: bool
    flagged: bool
    accuracy: float
    reason: str


async def evaluate_table(gt: dict, image: bytes) -> Outcome:
    settings = get_settings()
    parser = get_provider("parser")
    first = await parser.parse_table(
        image, TableCtx(locale_hint=gt.get("locale", "unknown")))

    if first.error or not first.records:
        # honest parse failure — correctly flagged, and it IS a wrong parse
        return Outcome(gt["table_id"], correct=False, flagged=True,
                       accuracy=0.0, reason="honest parse failure")

    parsed = {"html": first.html,
              "records": [r.model_dump() for r in first.records]}
    graded = grade.grade_table(gt, parsed)
    accuracy = (graded["correct_cells"] / graded["total_cells"]
                if graded["total_cells"] else 0.0)

    verifier = get_double_read_provider()
    if verifier is not None:  # cross-model second read
        second = await verifier.parse_table(
            image, TableCtx(locale_hint=gt.get("locale", "unknown")))
    else:  # same-model seed-shift
        second = await parser.parse_table(
            image, TableCtx(locale_hint=gt.get("locale", "unknown"), read_variant=1))
    second_records = ([r.model_dump() for r in second.records]
                      if not second.error and second.records else None)
    report = assess(
        first.html, parsed["records"], second_records,
        review_threshold=settings.confidence_review_threshold,
        agreement_threshold=settings.double_read_agreement_threshold)
    reason = ", ".join(f"{k}={v:.2f}"
                       for k, v in report.detail.get("signals", {}).items())
    return Outcome(gt["table_id"], correct=accuracy >= CORRECT_CELL_THRESHOLD,
                   flagged=report.needs_review, accuracy=accuracy, reason=reason)


async def evaluate() -> int:
    gt_paths = (sorted((SPIKE / "tables").glob("*/ground_truth.json"))
                + sorted((SPIKE / "tables_hard").glob("*/ground_truth.json")))
    if not gt_paths:
        sys.exit("no tables — run make_test_tables.py (+ make_hard_tables.py)")

    cfg = get_settings().models.parser
    print(f"flag-eval — parser {cfg.provider}@{cfg.base_url} {cfg.model_name}\n")
    print(f"{'table':38s} {'graded':>7s}  {'actual':7s} {'flag':7s}  signals")
    print("-" * 90)

    outcomes: list[Outcome] = []
    for gt_path in gt_paths:
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        if gt.get("_draft"):
            continue
        image = (gt_path.parent / "image.png").read_bytes()
        outcome = await evaluate_table(gt, image)
        outcomes.append(outcome)
        print(f"{outcome.table_id:38s} {outcome.accuracy:>6.0%}  "
              f"{'CORRECT' if outcome.correct else 'WRONG  '} "
              f"{'FLAGGED' if outcome.flagged else 'ok     '}  {outcome.reason}")

    correct = [o for o in outcomes if o.correct]
    wrong = [o for o in outcomes if not o.correct]
    fp = sum(1 for o in correct if o.flagged)
    caught = sum(1 for o in wrong if o.flagged)
    fp_rate = fp / len(correct) if correct else 0.0
    recall = caught / len(wrong) if wrong else 1.0

    print("-" * 90)
    print(f"correct parses: {len(correct)} | wrong parses: {len(wrong)}")
    print(f"false positives (correct but flagged): {fp}/{len(correct)} "
          f"= {fp_rate:.0%}  (DoD <= 10%: {'PASS' if fp_rate <= 0.10 else 'FAIL'})")
    print(f"recall (wrong and flagged):            {caught}/{len(wrong)} "
          f"= {recall:.0%}  (DoD >= 90%: {'PASS' if recall >= 0.90 else 'FAIL'})")
    return 0 if (fp_rate <= 0.10 and recall >= 0.90) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(evaluate()))
