"""Phase 0 spike: grade parsed tables against ground truth, cell by cell.

Matching philosophy: tolerant on *naming and shape*, strict on *localization
and values*:

- The VLM may invent dimension key names (spec Phase 2 §4) -> records are
  matched by dimension VALUES, never key names.
- The VLM may merge or split header values ("2013" + "T1" vs "2013 T1") ->
  fallback matching compares the multiset of whitespace tokens.
- The VLM may add extra dimensions (table title, units) -> a parsed record
  whose tokens are a superset of the ground-truth tokens still matches.
- But a parsed record MISSING ground-truth dimension tokens (e.g. one record
  per row with months folded into metric names) does NOT match: that is a
  real localization failure.
- A metric cell counts as correct when the matched record contains the exact
  ground-truth number (rel tol 1e-4, abs 0.01) among its metric values.

The report shows both strict (exact dimension-value match) and relaxed
accuracy; the DoD gate applies to relaxed. `--show-misses N` (default 2)
prints per-table diagnostics: unmatched ground-truth records next to the
nearest parsed record, honest-failure error messages, and the tail of the
raw model response — enough to debug prompts without opening files.

Usage: python spike/grade.py [--tables spike/tables] [--threshold 0.95]
                             [--show-misses 2]
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


def dim_tokens(dimensions: dict) -> Counter:
    tokens: Counter = Counter()
    for v in dimensions.values():
        tokens.update(t for t in norm_value(v).split(" ") if t)
    return tokens


def numbers_close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.01, 1e-4 * max(abs(a), abs(b)))


def metric_hits(gt_rec: dict, candidate: dict) -> int:
    cand_values = [v for v in candidate.get("metrics", {}).values()
                   if isinstance(v, (int, float))]
    return sum(
        1 for v in gt_rec["metrics"].values()
        if any(numbers_close(float(v), float(cv)) for cv in cand_values)
    )


def find_match(gt_rec: dict, parsed_records: list[dict],
               parsed_by_sig: dict) -> tuple[list[dict], int]:
    """Returns (candidates, level): 1 = exact dim values, 2 = token-equal,
    3 = parsed tokens ⊇ gt tokens, 0 = no match."""
    sig = dim_signature(gt_rec["dimensions"])
    if sig in parsed_by_sig:
        return parsed_by_sig[sig], 1
    gt_toks = dim_tokens(gt_rec["dimensions"])
    equal = [r for r in parsed_records
             if dim_tokens(r.get("dimensions", {})) == gt_toks]
    if equal:
        return equal, 2
    supersets = [r for r in parsed_records
                 if not (gt_toks - dim_tokens(r.get("dimensions", {})))]
    if supersets:
        return supersets, 3
    return [], 0


def jaccard(c1: Counter, c2: Counter) -> float:
    union = sum((c1 | c2).values())
    return sum((c1 & c2).values()) / union if union else 0.0


def grade_table(gt: dict, parsed: dict) -> dict:
    gt_records = gt["records"]
    total_cells = sum(len(r["metrics"]) for r in gt_records)
    base = {"table_id": gt["table_id"], "total_cells": total_cells,
            "gt_records": len(gt_records)}

    if "error" in parsed or "records" not in parsed:
        return {**base, "honest_failure": True,
                "error": parsed.get("error", "no records in parsed.json"),
                "correct_cells": 0, "strict_correct_cells": 0,
                "matched_records": 0, "parsed_records": 0, "misses": []}

    parsed_records = parsed["records"]
    parsed_by_sig: dict[frozenset, list[dict]] = {}
    for rec in parsed_records:
        parsed_by_sig.setdefault(
            dim_signature(rec.get("dimensions", {})), []).append(rec)

    correct = strict_correct = matched = 0
    misses: list[dict] = []
    for gt_rec in gt_records:
        candidates, level = find_match(gt_rec, parsed_records, parsed_by_sig)
        if not candidates:
            gt_toks = dim_tokens(gt_rec["dimensions"])
            nearest = max(
                parsed_records,
                key=lambda r: jaccard(gt_toks, dim_tokens(r.get("dimensions", {}))),
                default=None)
            misses.append({"kind": "unmatched", "gt": gt_rec, "nearest": nearest})
            continue
        matched += 1
        best = max(metric_hits(gt_rec, cand) for cand in candidates)
        correct += best
        if level == 1:
            strict_correct += best
        if best < len(gt_rec["metrics"]):
            misses.append({"kind": "wrong_values", "gt": gt_rec,
                           "nearest": candidates[0],
                           "missing_cells": len(gt_rec["metrics"]) - best})

    return {**base, "honest_failure": False, "error": None,
            "correct_cells": correct, "strict_correct_cells": strict_correct,
            "matched_records": matched, "parsed_records": len(parsed_records),
            "misses": misses}


def _fmt_rec(rec: dict | None) -> str:
    if rec is None:
        return "  (no parsed records at all)"
    return (f"  dims    = {json.dumps(rec.get('dimensions', {}), ensure_ascii=False)}\n"
            f"  metrics = {json.dumps(rec.get('metrics', {}), ensure_ascii=False)}")


def print_diagnostics(gt: dict, result: dict, table_dir: Path, limit: int) -> None:
    print(f"\n### {result['table_id']} — "
          f"{result['correct_cells']}/{result['total_cells']} cells, "
          f"{result['matched_records']}/{result['gt_records']} records matched "
          f"({result['parsed_records']} parsed)")

    if result["honest_failure"]:
        print(f"  contract error: {result['error']}")
        response = table_dir / "response.txt"
        if response.exists():
            tail = response.read_text(encoding="utf-8", errors="replace")[-500:]
            print("  raw response tail:")
            for line in tail.splitlines():
                print(f"  | {line}")
        return

    # structure summary: which keys did the model actually use?
    parsed_path = table_dir / "parsed.json"
    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    dim_keys = Counter()
    metric_keys = Counter()
    for rec in parsed.get("records", []):
        dim_keys.update(rec.get("dimensions", {}).keys())
        metric_keys.update(rec.get("metrics", {}).keys())
    print(f"  parsed dim keys:    {dict(dim_keys)}")
    print(f"  parsed metric keys: {dict(metric_keys)}")

    for miss in result["misses"][:limit]:
        if miss["kind"] == "unmatched":
            print("  MISS (no dim match) — ground truth:")
        else:
            print(f"  MISS ({miss['missing_cells']} wrong/missing values) — ground truth:")
        print(_fmt_rec(miss["gt"]))
        print("  nearest parsed record:")
        print(_fmt_rec(miss["nearest"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", type=Path, default=Path(__file__).parent / "tables")
    ap.add_argument("--threshold", type=float, default=0.95)
    ap.add_argument("--show-misses", type=int, default=2, metavar="N",
                    help="print up to N miss diagnostics per table (0 = off)")
    args = ap.parse_args()

    results: list[tuple[dict, dict, Path]] = []
    skipped = []
    for gt_path in sorted(args.tables.glob("*/ground_truth.json")):
        parsed_path = gt_path.parent / "parsed.json"
        if not parsed_path.exists():
            skipped.append(gt_path.parent.name)
            continue
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        results.append((gt, grade_table(gt, parsed), gt_path.parent))

    if not results:
        sys.exit("nothing to grade — run `python spike/parse_table.py --all` first")

    print(f"{'table':24s} {'diff.':8s} {'loc':3s} {'records':>9s} "
          f"{'strict':>8s} {'relaxed':>8s}")
    print("-" * 68)
    total_cells = total_correct = total_strict = 0
    for gt, r, _ in results:
        relaxed = r["correct_cells"] / r["total_cells"] if r["total_cells"] else 0.0
        strict = r["strict_correct_cells"] / r["total_cells"] if r["total_cells"] else 0.0
        total_cells += r["total_cells"]
        total_correct += r["correct_cells"]
        total_strict += r["strict_correct_cells"]
        note = "  [honest failure]" if r["honest_failure"] else ""
        print(f"{r['table_id']:24s} {gt['difficulty']:8s} {gt['locale']:3s} "
              f"{r['matched_records']:>4d}/{r['gt_records']:<4d} "
              f"{strict:>7.1%} {relaxed:>8.1%}{note}")

    overall = total_correct / total_cells
    overall_strict = total_strict / total_cells
    print("-" * 68)
    print(f"{'OVERALL':24s} {'':8s} {'':3s} "
          f"{total_correct:>4d}/{total_cells:<4d} "
          f"{overall_strict:>7.1%} {overall:>8.1%}")
    if skipped:
        print(f"\nnot yet parsed (skipped): {', '.join(skipped)}")

    if args.show_misses > 0:
        print("\n" + "=" * 68)
        print("DIAGNOSTICS (unmatched / wrong-value records, per table)")
        print("=" * 68)
        for gt, r, table_dir in results:
            if r["misses"] or r["honest_failure"]:
                print_diagnostics(gt, r, table_dir, args.show_misses)

    print(f"\nDoD gate (relaxed >= {args.threshold:.0%} of cells): "
          f"{'PASS' if overall >= args.threshold else 'FAIL'}")
    print("Record the result in spike/REPORT.md before moving past Phase 0.")
    sys.exit(0 if overall >= args.threshold else 1)


if __name__ == "__main__":
    main()
