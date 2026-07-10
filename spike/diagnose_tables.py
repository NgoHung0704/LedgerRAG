"""Diagnose table DETECTION on a real PDF (not parsing) — why a table is or
isn't found. For each page, prints how many tables each find_tables strategy
sees, their bbox / shape / fill-ratio, and what detect_tables() finally keeps
after dedup + guardrails.

Use it when a real document's table is missing from the Inspector (treated as
text): it tells you whether find_tables can see the table at all, or whether
our dedup/guardrail dropped it.

Usage:  python spike/diagnose_tables.py --pdf path/to/document.pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz  # noqa: E402

from tablerag.ingestion.layout import (  # noqa: E402
    accept_table,
    detect_tables,
    grid_fill_ratio,
)

STRATEGIES = ("lines_strict", "lines", "text")


def _bb(b) -> str:
    return f"({b[0]:.0f},{b[1]:.0f},{b[2]:.0f},{b[3]:.0f})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, type=Path)
    args = ap.parse_args()

    with fitz.open(args.pdf) as doc:
        for i, page in enumerate(doc):
            print(f"\n=== page {i + 1}  "
                  f"{page.rect.width:.0f}x{page.rect.height:.0f} ===")
            for strat in STRATEGIES:
                try:
                    tables = page.find_tables(strategy=strat).tables
                except Exception as e:  # noqa: BLE001
                    print(f"  {strat:12s}: ERROR {e}")
                    continue
                print(f"  {strat:12s}: {len(tables)} table(s)")
                for t in tables:
                    grid = t.extract()
                    n_rows = len(grid)
                    n_cols = max((len(r) for r in grid), default=0)
                    ok = accept_table(fitz.Rect(t.bbox), grid, strat, [])
                    print(f"       {_bb(t.bbox)}  {n_rows}x{n_cols}  "
                          f"fill={grid_fill_ratio(grid):.2f}  "
                          f"accept={'yes' if ok else 'NO'}")
            kept = detect_tables(page)
            print(f"  => detect_tables KEPT: {len(kept)}")
            for t, grid in kept:
                print(f"       {_bb(t.bbox)}  "
                      f"{len(grid)}x{max((len(r) for r in grid), default=0)}")


if __name__ == "__main__":
    main()
