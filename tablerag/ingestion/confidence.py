"""Phase 3 — confidence signals: the layer that knows when a parse is wrong.

No ground truth exists at runtime, so confidence is inferred from internal
consistency (SPEC Phase 3), via three independent signals:

1. Structural consistency — the cell count implied by the HTML (td slots,
   expanding rowspan/colspan) must accommodate the records' metric cells, and
   the record count must cover the HTML's data rows.
2. Double-read agreement — the table is parsed twice (second read with a
   different seed/temperature); the fraction of agreeing metric values below
   a threshold means the model is guessing. This is exactly the signal that
   catches rowspan-boundary confusions (the H/I-type misread): two reads
   diverge precisely where the model hesitates.
3. Arithmetic check — rows/columns labeled Total/Somme/Summe/... must equal
   the sum of their components (rounding tolerance). A failed sum is the
   strongest signal and flags immediately.

Signals are combined into a weighted confidence score; details are stored in
element.meta.confidence_detail for debugging. All thresholds are config.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

_TD_RE = re.compile(r"<td\b([^>]*)>", re.IGNORECASE)
_TR_RE = re.compile(r"<tr\b[^>]*>(.*?)(?=<tr\b|</table|$)", re.IGNORECASE | re.DOTALL)
_SPAN_RE = {
    "colspan": re.compile(r'colspan\s*=\s*"?(\d+)', re.IGNORECASE),
    "rowspan": re.compile(r'rowspan\s*=\s*"?(\d+)', re.IGNORECASE),
}
_KEEP_RE = re.compile(r"[^0-9a-z一-鿿]+")  # ascii alnum + CJK; rest -> space


def _norm(value: object) -> str:
    """Normalize a label for robust cross-read matching: lowercase, strip
    accents, drop punctuation/whitespace. So 'année'=='annee',
    "d'absentéisme"=='d absenteisme', 'Total général'=='total general' — the
    naming noise that made the double-read compare labels instead of
    coordinates (Phase 3 flag-eval false positives)."""
    s = str(value).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    return _KEEP_RE.sub(" ", s).strip()


# multilingual total labels, pre-normalized (C2: not one locale)
TOTAL_LABELS = frozenset(_norm(label) for label in (
    "total", "totaux", "somme", "ensemble", "sous-total", "total général",
    "subtotal", "grand total", "summe", "gesamt", "insgesamt", "zwischensumme",
    "totale", "suma", "总计", "合计",
))


@dataclass
class ConfidenceReport:
    confidence: float
    needs_review: bool
    detail: dict = field(default_factory=dict)


# ------------------------------------------------------------- signal 1

def structural_consistency(html: str, records: list[dict]) -> tuple[float, dict] | None:
    if not html or not records:
        return None
    slots = 0
    for attrs in _TD_RE.findall(html):
        colspan = int(m.group(1)) if (m := _SPAN_RE["colspan"].search(attrs)) else 1
        rowspan = int(m.group(1)) if (m := _SPAN_RE["rowspan"].search(attrs)) else 1
        slots += colspan * rowspan
    data_rows = sum(1 for row in _TR_RE.findall(html)
                    if _TD_RE.search(row))
    metric_cells = sum(len(r.get("metrics", {})) for r in records)

    cells_fit = 0 < metric_cells <= slots
    # long format ⇒ at least one record per data row (flat) or several (pivot)
    rows_covered = data_rows == 0 or len(records) >= data_rows
    score = 1.0 if (cells_fit and rows_covered) else 0.5 if (cells_fit or rows_covered) else 0.0
    return score, {"td_slots": slots, "data_rows": data_rows,
                   "metric_cells": metric_cells, "records": len(records)}


# ------------------------------------------------------------- signal 2

def _dim_tokens(record: dict) -> Counter:
    tokens: Counter = Counter()
    for value in record.get("dimensions", {}).values():
        for token in _norm(value).split(" "):
            if token:
                tokens[token] += 1
    return tokens


def _cells(records: list[dict]) -> list[tuple[Counter, float]]:
    """One entry per metric cell: (dimension-token multiset, rounded value)."""
    cells: list[tuple[Counter, float]] = []
    for record in records:
        tokens = _dim_tokens(record)
        for value in record.get("metrics", {}).values():
            if isinstance(value, (int, float)):
                cells.append((tokens, round(float(value), 2)))
    return cells


def _jaccard(a: Counter, b: Counter) -> float:
    union = sum((a | b).values())
    return sum((a & b).values()) / union if union else 1.0


def double_read_agreement(first: list[dict], second: list[dict],
                          coord_threshold: float = 0.5) -> tuple[float, dict]:
    """Fraction of metric cells on which two independent reads agree.

    Value-anchored, coordinate-fuzzy: a cell agrees when the other read has an
    (unused) cell with the SAME value whose dimension tokens overlap by at
    least `coord_threshold` (Jaccard). This is robust to key renaming and to
    accent/punctuation noise (same coordinates, different spelling still
    match) while still catching coordinate-SWAP misreads — the H/I-type error,
    where the same value lands on genuinely different coordinates in the two
    reads (low overlap -> no match -> disagreement)."""
    a_cells, b_cells = _cells(first), _cells(second)
    if not a_cells and not b_cells:
        return 0.0, {"cells_first": 0, "cells_second": 0, "agreed": 0}

    used = [False] * len(b_cells)
    agreed = 0
    for tokens_a, value_a in a_cells:
        best_i, best_j = -1, coord_threshold
        for i, (tokens_b, value_b) in enumerate(b_cells):
            if used[i] or value_b != value_a:
                continue
            j = _jaccard(tokens_a, tokens_b)
            if j >= best_j:
                best_j, best_i = j, i
        if best_i >= 0:
            used[best_i] = True
            agreed += 1

    score = 2 * agreed / (len(a_cells) + len(b_cells))
    return score, {"cells_first": len(a_cells), "cells_second": len(b_cells),
                   "agreed": agreed}


# ------------------------------------------------------------- signal 3

def _sum_close(total: float, component_sum: float) -> bool:
    return abs(total - component_sum) <= max(1.0, 1e-3 * abs(total))


def arithmetic_check(records: list[dict]) -> tuple[float, dict] | None:
    """Verify Total rows/columns against the sum of their components.
    Returns None when the table has no detectable totals."""
    normalized = [
        ({k: _norm(v) for k, v in r.get("dimensions", {}).items()},
         r.get("metrics", {}))
        for r in records
    ]
    checks = passed = 0
    failures: list[dict] = []
    for dims, metrics in normalized:
        total_keys = [k for k, v in dims.items() if v in TOTAL_LABELS]
        for key in total_keys:
            components = [
                m for d, m in normalized
                if d is not dims
                and d.get(key, "") not in TOTAL_LABELS
                and all(d.get(other) == dims.get(other)
                        for other in dims if other != key)
            ]
            if not components:
                continue
            for metric_key, total_value in metrics.items():
                if not isinstance(total_value, (int, float)):
                    continue
                component_sum = sum(
                    m.get(metric_key) for m in components
                    if isinstance(m.get(metric_key), (int, float)))
                checks += 1
                if _sum_close(float(total_value), float(component_sum)):
                    passed += 1
                else:
                    failures.append({"metric": metric_key,
                                     "total": total_value,
                                     "component_sum": component_sum})
    if checks == 0:
        return None
    return passed / checks, {"checks": checks, "passed": passed,
                             "failures": failures[:5]}


# ------------------------------------------------------------- combination

_WEIGHTS = {"structural": 0.2, "agreement": 0.35, "arithmetic": 0.45}


def assess(html: str, records: list[dict],
           second_records: list[dict] | None = None, *,
           review_threshold: float = 0.9,
           agreement_threshold: float = 0.98) -> ConfidenceReport:
    signals: dict[str, float] = {}
    detail: dict = {}

    if (structural := structural_consistency(html, records)) is not None:
        signals["structural"], detail["structural"] = structural
    if second_records is not None:
        signals["agreement"], detail["agreement"] = double_read_agreement(
            records, second_records)
    if (arithmetic := arithmetic_check(records)) is not None:
        signals["arithmetic"], detail["arithmetic"] = arithmetic

    if not signals:
        # nothing to judge with (e.g. no records at all) — do not fake certainty
        return ConfidenceReport(confidence=0.0, needs_review=True,
                                detail={"note": "no confidence signals available"})

    total_weight = sum(_WEIGHTS[name] for name in signals)
    confidence = sum(_WEIGHTS[name] * score for name, score in signals.items())
    confidence /= total_weight

    needs_review = confidence < review_threshold
    # a failed sum is the strongest signal: flag immediately (SPEC Phase 3)
    if signals.get("arithmetic", 1.0) < 0.999:
        needs_review = True
    if "agreement" in signals and signals["agreement"] < agreement_threshold:
        needs_review = True

    detail["signals"] = {k: round(v, 4) for k, v in signals.items()}
    detail["confidence"] = round(confidence, 4)
    return ConfidenceReport(confidence=round(confidence, 4),
                            needs_review=needs_review, detail=detail)
