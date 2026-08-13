"""Detection gate: are the tables on a real page FOUND at all?

`make eval-tables` grades how well a table is READ, from images already cropped
in spike/tables/. It never asks whether the platform would have found that table
on the page. So a detector can miss the main table of every document in a corpus
and the table gate still reads 88.4 %.

That is not hypothetical. Measured on the box, `EPSENS DEFIS - 100005.pdf` had
ONE table element in the whole document — the risk indicators on page 2 — while
its three performance tables on page 1 were never detected. Every retrieval fix
of that day was therefore powerless on the question "performance cumulée sur
5 ans": the value 50,46 existed nowhere except as page prose.

What is graded here:

  tables    — how many regions the platform accepts on the page, against how
              many a reader sees. Reported, not gated on its own: one detection
              covering two adjacent tables is a different fault from none.
  reachable — whether a specific printed value can be found in ANY accepted
              grid. This is the one that matters, because it is exactly the
              question "could an answer have cited a table for this number".

Drop the PDFs named in detection.jsonl into tests/eval/tables/pdfs/.
No model is called: detection is pure PyMuPDF plus this repo's acceptance rules,
so this runs anywhere the file does.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import fitz

from tablerag.ingestion.layout import detect_tables

# a number printed as 50,46 may be extracted as "50,46" or "50, 46"; compare on
# digits and the separator alone so a spacing artefact is not read as a miss
_TIGHTEN = re.compile(r"\s+")


def _flat(grid) -> str:
    return _TIGHTEN.sub("", " ".join(str(cell or "") for row in grid for cell in row))


def reachable(grids: list, value: str) -> bool:
    """Is this printed value inside any accepted grid?"""
    needle = _TIGHTEN.sub("", value)
    return any(needle in _flat(grid) for grid in grids)


def grade(item: dict, grids: list) -> tuple[bool, str]:
    found = len(grids)
    missing = [v for v in item.get("must_reach", []) if not reachable(grids, v)]
    if missing:
        return False, (f"{found}/{item['tables']} tables; "
                       f"unreachable: {', '.join(missing)}")
    return True, f"{found}/{item['tables']} tables; all values reachable"


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=here / "detection.jsonl")
    ap.add_argument("--pdf-dir", type=Path, default=here / "pdfs")
    args = ap.parse_args()

    items = [json.loads(line) for line in
             args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]

    print(f"{'id':16} {'verdict':8} detail")
    print("-" * 78)
    passed = ran = 0
    for item in items:
        path = args.pdf_dir / item["pdf"]
        if not path.exists():
            print(f"{item['id']:16} {'SKIP':8} not in {args.pdf_dir}: {item['pdf']}")
            continue
        ran += 1
        with fitz.open(path) as doc:
            page = doc[item["page"] - 1]
            grids = [grid for _, grid in detect_tables(page)]
        ok, detail = grade(item, grids)
        passed += ok
        print(f"{item['id']:16} {'PASS' if ok else 'FAIL':8} {detail}")
        if not ok and item.get("note"):
            print(f"{'':16} {'':8} {item['note']}")

    print("-" * 78)
    if not ran:
        print(f"nothing ran — drop the PDFs into {args.pdf_dir}")
        raise SystemExit(1)
    pct = 100 * passed / ran
    print(f"pages where every value is reachable: {passed}/{ran} = {pct:.0f}% "
          f"(target >= 95%: {'PASS' if pct >= 95 else 'FAIL'})")
    raise SystemExit(0 if pct >= 95 else 1)


if __name__ == "__main__":
    main()
