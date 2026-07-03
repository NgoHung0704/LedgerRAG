"""Phase 0 spike: grade parsed tables against ground truth, cell by cell.

Grading is deliberately tolerant to *naming* and strict on *values*:

- The VLM is allowed to invent dimension key names (spec Phase 2 §4), so
  records are matched by the multiset of their normalized dimension VALUES,
  not by key names.
- A metric cell counts as correct when the matched parsed record contains the
  ground-truth numeric value among its metric values (relative tolerance 1e-4,
  absolute 0.01) — metric key names are also free.

Prints a per-table report and exits non-zero when overall cell accuracy is
below the DoD threshold (95%).

Usage: python spike/grade.py [--tables spike/tables] [--threshold 0.95]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

WS_RE = re.compile(r"\s+")


def norm_value(v: object) -> str:
    s = str(v).strip().lower()
    # unify exotic spaces (U+202F, U+00A0, ...) before collapsing
    s = "".join(" " if unicodedata.category(c) == "Zs" else c for c in s)
    return WS_RE.sub(" ", s)


def dim_signature(dimensions: dict) -> frozenset:
    return frozenset(Counter(norm_value(v) for v in dimensions.values()).items())


def numbers_close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.01, 1e-4 * max(abs(a), abs(b)))


def grade_table(gt: dict, parsed: dict) -> dict:
    gt_records = gt["records"]
    total_cells = sum(len(r["metrics"]) for r in gt_records)

    if "error" in parsed or "records" not in parsed:
        return {"table_id": gt["table_id"], "honest_failure": True,
                "total_cells": total_cells, "correct_cells": 0,
                "matched_records": 0, "gt_records": len(gt_records),
                "parsed_records": 0}

    parsed_by_sig: dict[frozenset, list[dict]] = {}
    for rec in parsed["records"]:
        parsed_by_sig.setdefault(dim_signature(rec.get("dimensions", {})), []).append(rec)

    correct = 0
    matched = 0
    for gt_rec in gt_records:
        candidates = parsed_by_sig.get(dim_signature(gt_rec["dimensions"]), [])
        if not candidates:
            continue
        matched += 1
        # grade against the best candidate (normally exactly one)
        best = 0
        for cand in candidates:
            cand_values = [v for v in cand.get("metrics", {}).values()
                           if isinstance(v, (int, float))]
            hits = sum(
                1 for v in gt_rec["metrics"].values()
                if any(numbers_close(float(v), float(cv)) for cv in cand_values)
            )
            best = max(best, hits)
        correct += best

    return {"table_id": gt["table_id"], "honest_failure": False,
            "total_cells": total_cells, "correct_cells": correct,
            "matched_records": matched, "gt_records": len(gt_records),
            "parsed_records": len(parsed["records"])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", type=Path, default=Path(__file__).parent / "tables")
    ap.add_argument("--threshold", type=float, default=0.95)
    args = ap.parse_args()

    results = []
    skipped = []
    for gt_path in sorted(args.tables.glob("*/ground_truth.json")):
        parsed_path = gt_path.parent / "parsed.json"
        if not parsed_path.exists():
            skipped.append(gt_path.parent.name)
            continue
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        results.append((gt, grade_table(gt, parsed)))

    if not results:
        sys.exit("nothing to grade — run `python spike/parse_table.py --all` first")

    print(f"{'table':24s} {'difficulty':9s} {'loc':3s} {'records':>9s} "
          f"{'cells':>11s} {'accuracy':>9s}")
    print("-" * 72)
    total_cells = total_correct = 0
    for gt, r in results:
        acc = r["correct_cells"] / r["total_cells"] if r["total_cells"] else 0.0
        total_cells += r["total_cells"]
        total_correct += r["correct_cells"]
        note = "  [honest failure]" if r["honest_failure"] else ""
        print(f"{r['table_id']:24s} {gt['difficulty']:9s} {gt['locale']:3s} "
              f"{r['matched_records']:>4d}/{r['gt_records']:<4d} "
              f"{r['correct_cells']:>5d}/{r['total_cells']:<5d} {acc:>8.1%}{note}")

    overall = total_correct / total_cells
    print("-" * 72)
    print(f"{'OVERALL':24s} {'':9s} {'':3s} {'':>9s} "
          f"{total_correct:>5d}/{total_cells:<5d} {overall:>8.1%}")
    if skipped:
        print(f"\nnot yet parsed (skipped): {', '.join(skipped)}")

    print(f"\nDoD gate (>= {args.threshold:.0%} of cells correct): "
          f"{'PASS' if overall >= args.threshold else 'FAIL'}")
    print("Record the result in spike/REPORT.md before moving past Phase 0.")
    sys.exit(0 if overall >= args.threshold else 1)


if __name__ == "__main__":
    main()
